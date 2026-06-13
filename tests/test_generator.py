"""Generator / rendering tests (Slice 0 + Slice 1 templates).

These are fast: they render templates and inspect output without running uv,
network, or Docker. End-to-end runnability lives in ``test_golden.py``.
"""

from __future__ import annotations

import py_compile
from pathlib import Path

import pytest
import yaml

from harnessmith.generator import TargetExistsError, generate, launch_script_stem
from harnessmith.presets import preset_mcp_servers, preset_spec_path
from harnessmith.spec import load_spec

EXAMPLE_SPEC = Path(__file__).resolve().parents[1] / "examples" / "spec.yaml"


@pytest.fixture
def spec():
    return load_spec(EXAMPLE_SPEC)


@pytest.fixture
def preset_spec():
    return load_spec(preset_spec_path("coding-assistant"))


def test_generates_expected_file_structure(tmp_path, spec):
    out = tmp_path / "my-agent"
    result = generate(spec, out, git_init=False)

    expected = [
        out / "pyproject.toml",
        out / "README.md",
        out / ".env.example",
        out / "LICENSE",
        out / ".gitignore",
        out / "harness.spec.yaml",
        out / "src" / "agent_harness" / "__init__.py",
    ]
    for path in expected:
        assert path.is_file(), f"missing {path}"
    assert out / "harness.spec.yaml" in result.written_files


def test_placeholders_are_replaced(tmp_path, spec):
    out = tmp_path / "my-agent"
    generate(spec, out, git_init=False)

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "agent_harness"' in pyproject
    assert "{{" not in pyproject  # no unrendered Jinja left

    init_py = (out / "src" / "agent_harness" / "__init__.py").read_text(encoding="utf-8")
    assert "agent_harness — an agent harness" in init_py
    assert "__project_slug__" not in init_py


def test_env_example_lists_env_names_only(tmp_path, spec):
    out = tmp_path / "my-agent"
    generate(spec, out, git_init=False)

    env_example = (out / ".env.example").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" in env_example
    assert "OPENAI_BASE_URL=" in env_example
    assert "sk-" not in env_example  # never a real value


def test_spec_snapshot_has_no_plaintext_secret(tmp_path, spec):
    out = tmp_path / "my-agent"
    generate(spec, out, git_init=False)

    snapshot = (out / "harness.spec.yaml").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in snapshot  # the env NAME is recorded
    assert "sk-" not in snapshot  # but no secret value
    # the snapshot must round-trip back into a valid spec
    reloaded = load_spec(out / "harness.spec.yaml")
    assert reloaded.project_slug == spec.project_slug


def test_generated_pyproject_has_no_agent_framework(tmp_path, spec):
    out = tmp_path / "my-agent"
    generate(spec, out, git_init=False)

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8").lower()
    for forbidden in ("langchain", "langgraph", "adk"):
        assert forbidden not in pyproject, f"{forbidden} must not appear in generated pyproject"


def test_rerun_does_not_overwrite(tmp_path, spec):
    out = tmp_path / "my-agent"
    generate(spec, out, git_init=False)

    # user edits a file
    readme = out / "README.md"
    readme.write_text("MY EDITS", encoding="utf-8")

    with pytest.raises(TargetExistsError):
        generate(spec, out, git_init=False)

    assert readme.read_text(encoding="utf-8") == "MY EDITS"  # untouched


def test_empty_existing_dir_is_allowed(tmp_path, spec):
    out = tmp_path / "empty"
    out.mkdir()
    generate(spec, out, git_init=False)
    assert (out / "pyproject.toml").is_file()


def test_git_init_creates_repo(tmp_path, spec):
    out = tmp_path / "my-agent"
    result = generate(spec, out, git_init=True)
    assert result.git_initialized is True
    assert (out / ".git").is_dir()


# --- Slice 1: harness core + runnability templates -------------------------


def test_generates_harness_core_modules(tmp_path, preset_spec):
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    pkg = out / "src" / "coding_assistant"
    for module in ("config", "llm", "loop", "tools", "hooks", "trace", "prompts", "mock"):
        assert (pkg / "harness" / f"{module}.py").is_file(), module
    assert (pkg / "interfaces" / "cli.py").is_file()
    assert (out / "tests" / "test_harness.py").is_file()


def test_generates_runnability_files(tmp_path, preset_spec):
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    for path in (
        out / "config.yaml",
        out / ".python-version",
        out / "Dockerfile",
        out / ".dockerignore",
        out / ".devcontainer" / "devcontainer.json",
        out / "AGENTS.md",
    ):
        assert path.is_file(), path
    assert (out / ".python-version").read_text().strip() == "3.14"


def test_rendered_python_modules_compile(tmp_path, preset_spec):
    """Every generated .py file must be syntactically valid Python."""
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    py_files = sorted(out.rglob("*.py"))
    assert py_files
    for path in py_files:
        py_compile.compile(str(path), doraise=True)


def test_no_unrendered_jinja_in_text_files(tmp_path, preset_spec):
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".toml", ".yaml", ".md", ".json"}:
            text = path.read_text(encoding="utf-8")
            assert "{{" not in text and "{%" not in text, f"unrendered jinja in {path}"


def test_pyproject_has_runtime_deps_and_no_framework(tmp_path, preset_spec):
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8")
    for dep in ("openai", "pydantic", "pydantic-settings", "pyyaml", "typer"):
        assert dep in pyproject, dep
    lowered = pyproject.lower()
    for forbidden in ("langchain", "langgraph", "adk"):
        assert forbidden not in lowered, forbidden


def test_config_yaml_renders_from_spec_without_secrets(tmp_path, preset_spec):
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    config = (out / "config.yaml").read_text(encoding="utf-8")
    assert "project_slug: coding_assistant" in config
    assert "api_key_env: OPENAI_API_KEY" in config  # env NAME only
    assert "get_current_time" in config and "calculator" in config
    # Per-LLM cost accounting / limit knobs (the Budget page edits these); no
    # per-run budget block anymore.
    assert "cost_limit:" in config and "input_cost_per_million:" in config
    assert "budget:" not in config
    assert "sk-" not in config  # never a real secret value


def test_default_system_prompt_round_trips_and_matches_fallback(tmp_path, spec):
    """The baked default system prompt renders as a readable YAML literal block
    that round-trips byte-for-byte, and the generated harness/prompts.py reuses the
    same text as its empty-config fallback (so behavior is identical either way)."""
    from harnessmith.scaffold import DEFAULT_SYSTEM_PROMPT

    # The generic example spec seeds exactly the canonical default.
    assert spec.prompts.system == DEFAULT_SYSTEM_PROMPT

    out = tmp_path / "thin"
    generate(spec, out, git_init=False)
    config = yaml.safe_load((out / "config.yaml").read_text(encoding="utf-8"))
    # Multi-line literal block survives a yaml round-trip unchanged (no escaping,
    # no trailing newline, blank lines between paragraphs preserved).
    assert config["prompts"]["system"] == DEFAULT_SYSTEM_PROMPT

    prompts_py = (out / "src" / "agent_harness" / "harness" / "prompts.py").read_text(
        encoding="utf-8"
    )
    assert DEFAULT_SYSTEM_PROMPT in prompts_py  # runtime fallback == baked seed


def test_debug_log_is_generated_off_by_default_and_gitignored(tmp_path, preset_spec):
    """The opt-in local debug log ships in every product: module present,
    config knob rendered (default off), and its dir never reaches git."""
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    assert (out / "src" / "coding_assistant" / "harness" / "debuglog.py").is_file()
    config = yaml.safe_load((out / "config.yaml").read_text(encoding="utf-8"))
    assert config["observability"]["debug"] is False
    assert config["observability"]["debug_dir"] == "logs"
    assert "logs/" in (out / ".gitignore").read_text(encoding="utf-8")


def test_rules_injection_mechanism_is_always_generated(tmp_path, spec):
    """Even with no rule files seeded, prompts.py carries the always-apply rules
    mechanism and config.yaml exposes the (empty) runtime knob — but no unused
    RULES.md is dropped into the repo."""
    out = tmp_path / "thin"
    generate(spec, out, git_init=False)
    prompts_py = (out / "src" / "agent_harness" / "harness" / "prompts.py").read_text(
        encoding="utf-8"
    )
    assert "_load_rules" in prompts_py and "rules_files" in prompts_py
    assert "rules_files: []" in (out / "config.yaml").read_text(encoding="utf-8")
    assert not (out / "RULES.md").exists()  # no rule file referenced -> none shipped


def test_rules_starter_file_generated_when_seeded(tmp_path, preset_spec):
    """The coding-assistant preset seeds prompts.rules_files: [RULES.md], so a
    starter RULES.md is generated, the runtime knob points at it, and the seed
    (a recipe input) lands in the committed spec snapshot."""
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    assert (out / "RULES.md").is_file()
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "rules_files:" in config_yaml and "RULES.md" in config_yaml
    assert "RULES.md" in (out / "harness.spec.yaml").read_text(encoding="utf-8")


# --- Slice 5: loop paradigms (registry always; built-ins conditional) ------


def test_paradigm_registry_and_agent_are_always_generated(tmp_path, preset_spec):
    """Default (paradigms: [agent]) still ships the registry + agent, plus the
    runtime paradigms config — but not the other built-ins."""
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    pdir = out / "src" / "coding_assistant" / "harness" / "paradigms"
    assert (pdir / "__init__.py").is_file()
    assert (pdir / "agent.py").is_file()
    assert not (pdir / "plan.py").exists()
    assert not (pdir / "ask.py").exists()

    config_py = (out / "src" / "coding_assistant" / "harness" / "config.py").read_text(encoding="utf-8")
    assert "class ParadigmsConfig" in config_py
    assert "paradigms: ParadigmsConfig" in config_py

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "paradigms:" in config_yaml
    assert "enabled: [agent]" in config_yaml
    assert "default: agent" in config_yaml


def test_multi_paradigm_generates_all_builtin_files(tmp_path, spec):
    spec.paradigms = ["agent", "plan", "ask"]
    out = tmp_path / "multi"
    generate(spec, out, git_init=False)
    pdir = out / "src" / "agent_harness" / "harness" / "paradigms"
    for name in ("__init__", "agent", "plan", "ask"):
        assert (pdir / f"{name}.py").is_file(), name

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "enabled: [agent, plan, ask]" in config_yaml
    assert "default: agent" in config_yaml


def test_paradigm_files_do_not_import_each_other(tmp_path, spec):
    """Decoupling gate: built-in paradigms must not import one another."""
    spec.paradigms = ["agent", "plan", "ask"]
    out = tmp_path / "multi"
    generate(spec, out, git_init=False)
    pdir = out / "src" / "agent_harness" / "harness" / "paradigms"
    builtins = ["agent", "plan", "ask"]
    for name in builtins:
        text = (pdir / f"{name}.py").read_text(encoding="utf-8")
        for other in builtins:
            if other == name:
                continue
            assert f"from . import {other}" not in text, f"{name} imports {other}"
            assert f"from .{other}" not in text, f"{name} imports {other}"
            assert f"import {other}\n" not in text, f"{name} imports {other}"


def test_loop_is_a_thin_dispatcher(tmp_path, preset_spec):
    """loop.py no longer holds the loop body — it dispatches to a paradigm."""
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    loop = (out / "src" / "coding_assistant" / "harness" / "loop.py").read_text(encoding="utf-8")
    assert "get_paradigm" in loop
    assert "from .paradigms import RunResult, get_paradigm" in loop


# --- Slice 3: optional web interface (conditional generation) --------------


def test_web_disabled_omits_web_files_and_deps(tmp_path, preset_spec):
    """Default (web: false) repo has zero web footprint — stays thin."""
    out = tmp_path / "noweb"
    generate(preset_spec, out, git_init=False)
    pkg = out / "src" / "coding_assistant"
    assert not (pkg / "interfaces" / "web.py").exists()
    assert not (pkg / "interfaces" / "web_index.html").exists()
    assert not (out / "tests" / "test_web.py").exists()

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "fastapi" not in pyproject
    assert "uvicorn" not in pyproject
    assert "httpx" not in pyproject
    assert "ruamel" not in pyproject  # comment-preserving write-back is web-only

    cli = (pkg / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert "def serve(" not in cli


def test_web_enabled_generates_web_files_and_deps(tmp_path, spec):
    spec.interfaces.web = True
    out = tmp_path / "web"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    assert (pkg / "interfaces" / "web.py").is_file()
    assert (pkg / "interfaces" / "web_index.html").is_file()
    assert (out / "tests" / "test_web.py").is_file()

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8")
    assert "fastapi" in pyproject and "uvicorn" in pyproject
    assert "httpx" in pyproject  # test dep for fastapi.testclient
    assert "ruamel.yaml" in pyproject  # comment-preserving /config write-back
    # never an agent framework, even with web enabled
    lowered = pyproject.lower()
    for forbidden in ("langchain", "langgraph", "adk"):
        assert forbidden not in lowered

    cli = (pkg / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert "def serve(" in cli

    # web.py is valid Python even though fastapi isn't installed in this dev env
    py_compile.compile(str(pkg / "interfaces" / "web.py"), doraise=True)


def test_web_index_has_no_unrendered_jinja(tmp_path, spec):
    spec.interfaces.web = True
    out = tmp_path / "web"
    generate(spec, out, git_init=False)
    html = (out / "src" / "agent_harness" / "interfaces" / "web_index.html").read_text(
        encoding="utf-8"
    )
    assert "{{" not in html and "{%" not in html
    assert "agent_harness" in html  # project_slug was rendered into the title


# --- Slice 7: display_name, context seeding, paged config panel ------------


def test_display_name_renders_in_titles_and_readme(tmp_path, spec):
    spec.display_name = "Friendly Bot"
    spec.interfaces.web = True
    out = tmp_path / "named"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    assert (out / "README.md").read_text(encoding="utf-8").splitlines()[0] == "# Friendly Bot"
    assert 'FastAPI(title="Friendly Bot — web")' in (pkg / "interfaces" / "web.py").read_text(
        encoding="utf-8"
    )
    idx = (pkg / "interfaces" / "web_index.html").read_text(encoding="utf-8")
    assert "<title>Friendly Bot — web</title>" in idx
    # the slug still drives the package/folder, not the display name
    assert (pkg / "harness" / "loop.py").is_file()


def test_display_name_falls_back_to_slug(tmp_path, spec):
    """The example spec has no display_name -> titles use project_slug."""
    out = tmp_path / "fallback"
    generate(spec, out, git_init=False)
    assert (out / "README.md").read_text(encoding="utf-8").splitlines()[0] == "# agent_harness"


def test_context_block_seeds_from_spec(tmp_path, spec):
    spec.context = {
        "strategy": "truncate",
        "keep_last_turns": 3,
        "combine": "and",
        "triggers": {"max_tokens": 4000, "max_turns": 20},
    }
    out = tmp_path / "ctx"
    generate(spec, out, git_init=False)
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "strategy: truncate" in config_yaml
    assert "keep_last_turns: 3" in config_yaml
    assert "combine: and" in config_yaml
    assert "max_tokens: 4000" in config_yaml
    assert "max_turns: 20" in config_yaml


def test_context_block_defaults_when_spec_omits_it(tmp_path, spec):
    out = tmp_path / "ctx_default"
    generate(spec, out, git_init=False)
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "strategy: summarize" in config_yaml  # default trigger compacts at 192k
    assert "keep_last_turns: 6" in config_yaml
    assert "combine: or" in config_yaml
    assert "max_tokens: 192000" in config_yaml  # the default token trigger


def test_web_index_has_paged_config_and_language_switch(tmp_path, preset_spec):
    preset_spec.interfaces.web = True
    out = tmp_path / "paged"
    generate(preset_spec, out, git_init=False)
    idx = (out / "src" / "coding_assistant" / "interfaces" / "web_index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="sys-lang"' in idx and "中文" in idx  # language switch (en/zh), on the System tab
    assert 'id="cfg-tabs"' in idx  # config is paged by function
    for sub in (
        "subtab_llm", "subtab_context", "subtab_budget", "subtab_tools",
        "subtab_prompts", "subtab_paradigms", "subtab_observability", "subtab_system",
    ):
        assert sub in idx
    # System tab + sidebar theme toggle (light/dark) ship with the web interface
    assert 'data-cfg="system"' in idx and 'id="theme-toggle"' in idx
    assert "html.dark" in idx  # contained dark-theme override
    assert "/system/config-export" in idx and "/system/config-import" in idx


def test_web_surfaces_registered_extensions(tmp_path, preset_spec):
    """The Context/Paradigms tabs are built from a /registries endpoint, so a
    custom @register_* shows up; config names that aren't registered are flagged."""
    preset_spec.interfaces.web = True
    out = tmp_path / "registries"
    generate(preset_spec, out, git_init=False)
    base = out / "src" / "coding_assistant"
    web_py = (base / "interfaces" / "web.py").read_text(encoding="utf-8")
    idx = (base / "interfaces" / "web_index.html").read_text(encoding="utf-8")
    cli_py = (base / "interfaces" / "cli.py").read_text(encoding="utf-8")

    # backend introspection endpoint reads the live registries (no secrets)
    assert '"/registries"' in web_py
    assert "STRATEGIES" in web_py and "CONDITIONS" in web_py and "PARADIGMS" in web_py
    # frontend builds the dropdowns/checklist from it + hints + mismatch flag
    assert "/registries" in idx
    assert 'id="cfg-ctx-triggers"' in idx and 'id="cfg-par-list"' in idx
    assert "ctx_extend_hint" in idx and "par_extend_hint" in idx
    assert "cfg_unregistered" in idx
    # CLI introspection mirrors it (available even without web)
    assert "def info(" in cli_py


def test_language_seeds_product_web_default(tmp_path, spec):
    """spec.language threads into the product web's default UI language."""
    spec.interfaces.web = True
    spec.language = "zh"
    out = tmp_path / "lang_zh"
    generate(spec, out, git_init=False)
    idx = (out / "src" / "agent_harness" / "interfaces" / "web_index.html").read_text(
        encoding="utf-8"
    )
    assert 'localStorage.getItem("hf_lang") || "zh"' in idx


def test_language_defaults_to_en_in_product_web(tmp_path, spec):
    spec.interfaces.web = True
    out = tmp_path / "lang_en"
    generate(spec, out, git_init=False)
    idx = (out / "src" / "agent_harness" / "interfaces" / "web_index.html").read_text(
        encoding="utf-8"
    )
    assert 'localStorage.getItem("hf_lang") || "en"' in idx


# --- Slice 4: optional MCP tools (conditional generation) ------------------


def test_mcp_disabled_omits_mcp_files_and_deps(tmp_path, spec):
    """A spec with mcp.enabled=false has zero MCP footprint — stays thin.

    (The coding-assistant preset is now an MCP baseline, so the thin assertion
    uses the plain example spec instead.)"""
    out = tmp_path / "nomcp"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"
    assert not (pkg / "harness" / "mcp.py").exists()
    assert not (out / "tests" / "test_mcp.py").exists()
    assert not (out / "tests" / "_mcp_dummy_server.py").exists()

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "mcp" not in pyproject

    config_py = (pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "McpConfig" not in config_py and "mcp" not in config_py.lower()

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8").lower()
    assert "mcp" not in config_yaml


def test_mcp_enabled_generates_files_and_deps(tmp_path, spec):
    spec.mcp.enabled = True
    out = tmp_path / "mcp"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    assert (pkg / "harness" / "mcp.py").is_file()
    assert (out / "tests" / "test_mcp.py").is_file()
    assert (out / "tests" / "_mcp_dummy_server.py").is_file()

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8")
    assert "mcp>=" in pyproject
    lowered = pyproject.lower()
    for forbidden in ("langchain", "langgraph", "adk"):
        assert forbidden not in lowered  # never an agent framework, even with MCP

    config_py = (pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "mcp: McpConfig" in config_py
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    # No prefill passed -> empty server list (still a runtime knob).
    assert "mcp:" in config_yaml and "servers: []" in config_yaml

    # mcp.py is valid Python even though the mcp SDK isn't installed in this dev env
    py_compile.compile(str(pkg / "harness" / "mcp.py"), doraise=True)


def test_serve_warms_mcp_in_background_not_blocking_the_port(tmp_path, spec):
    """With web + MCP, `serve` must NOT block the web port on MCP warm-up: the
    servers' first launch (uvx/npx cold start) can be slow, so it runs on a
    background thread and the port binds immediately. Guard against a regression
    back to a blocking `_ensure_mcp_manager(application)` call."""
    spec.interfaces.web = True
    spec.mcp.enabled = True
    out = tmp_path / "serve_warm"
    generate(spec, out, git_init=False)
    cli = (out / "src" / "agent_harness" / "interfaces" / "cli.py").read_text(encoding="utf-8")
    serve_body = cli.split("def serve(", 1)[1].split("\ndef ", 1)[0]
    assert "_ensure_mcp_manager" in serve_body  # still warmed proactively
    assert "Thread(" in serve_body and "daemon=True" in serve_body  # but off-thread
    # and the warm is kicked off before uvicorn binds (so it actually starts)
    assert serve_body.index("Thread(") < serve_body.index("uvicorn.run(")
    py_compile.compile(str(out / "src" / "agent_harness" / "interfaces" / "cli.py"), doraise=True)


# --- Slice 6: MCP capability baseline (catalog prefill into config.yaml) ----


def test_coding_assistant_is_an_mcp_baseline(tmp_path, preset_spec):
    """coding-assistant now enables MCP and carries the baseline dependency."""
    out = tmp_path / "ca"
    generate(preset_spec, out, git_init=False)
    pkg = out / "src" / "coding_assistant"
    assert (pkg / "harness" / "mcp.py").is_file()
    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8")
    assert "mcp>=" in pyproject


def test_mcp_prefill_writes_servers_and_allowlist_to_config(tmp_path, preset_spec):
    """The baseline prefill lands fetch/git/DC in config.yaml, each enabled by a
    single ``<server>__*`` wildcard (the whole toolset on by default)."""
    out = tmp_path / "ca"
    servers = preset_mcp_servers("coding-assistant")
    generate(preset_spec, out, git_init=False, mcp_servers=servers)

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    # servers prefilled into the runtime file
    assert "command: uvx" in config_yaml
    assert "mcp-server-fetch" in config_yaml
    assert "duckduckgo-mcp-server" in config_yaml  # keyless web search
    assert "mcp-server-git" in config_yaml
    assert "@wonderwhy-er/desktop-commander@latest" in config_yaml
    # safe read tools marked for read-only paradigms + a description per server
    assert "safe_tools:" in config_yaml and "description:" in config_yaml

    config = yaml.safe_load(config_yaml)
    enabled = {t["name"] for t in config["tools"] if t["enabled"]}
    # Every prefilled server is enabled via its wildcard — all tools on by default.
    assert {"fetch__*", "ddg-search__*", "git__*", "desktop-commander__*"} <= enabled

    # Desktop Commander's read tools land in safe_tools so the read-only plan/ask
    # paradigms can read files/list dirs/search code; write/shell stay high-risk.
    dc = next(s for s in config["mcp"]["servers"] if s["name"] == "desktop-commander")
    assert "read_file" in dc["safe_tools"] and "list_directory" in dc["safe_tools"]
    assert "write_file" not in dc["safe_tools"] and "start_process" not in dc["safe_tools"]


def test_mcp_prefill_servers_do_not_leak_into_spec_snapshot(tmp_path, preset_spec):
    """Servers are a runtime knob: they go to config.yaml, never the spec/snapshot."""
    out = tmp_path / "ca"
    servers = preset_mcp_servers("coding-assistant")
    generate(preset_spec, out, git_init=False, mcp_servers=servers)

    snapshot = (out / "harness.spec.yaml").read_text(encoding="utf-8")
    assert "uvx" not in snapshot
    assert "mcp-server-fetch" not in snapshot
    assert "servers" not in snapshot
    # the snapshot still round-trips into a valid spec (mcp only as enabled flag)
    reloaded = load_spec(out / "harness.spec.yaml")
    assert reloaded.mcp.enabled is True


def test_mcp_prefill_bakes_uvx_servers_into_dockerfile(tmp_path, preset_spec):
    """uvx servers are baked into the image; Node-based DC is not."""
    out = tmp_path / "ca"
    servers = preset_mcp_servers("coding-assistant")
    generate(preset_spec, out, git_init=False, mcp_servers=servers)

    dockerfile = (out / "Dockerfile").read_text(encoding="utf-8")
    assert "uvx mcp-server-fetch --help" in dockerfile
    assert "uvx duckduckgo-mcp-server --help" in dockerfile
    assert "uvx mcp-server-git --help" in dockerfile
    assert "UV_OFFLINE=1" in dockerfile  # forced offline at container runtime
    assert "desktop-commander" not in dockerfile  # Node-based, not baked


def test_mcp_disabled_ignores_prefill(tmp_path, spec):
    """Prefill only applies when mcp.enabled — otherwise zero MCP footprint."""
    from harnessmith.catalog import resolve_servers

    out = tmp_path / "nomcp"
    generate(spec, out, git_init=False, mcp_servers=resolve_servers(["fetch"]))
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8").lower()
    assert "mcp" not in config_yaml
    assert "fetch__" not in config_yaml


# --- Slice 6: standard Agent Skills (opt-in, skills.enabled) ----------------


def test_skills_disabled_omits_skills_footprint(tmp_path, preset_spec):
    """Default (skills.enabled=false) repo has zero skills footprint — stays thin."""
    out = tmp_path / "noskills"
    generate(preset_spec, out, git_init=False)
    pkg = out / "src" / "coding_assistant"
    assert not (pkg / "harness" / "skills.py").exists()
    assert not (out / "tests" / "test_skills.py").exists()
    assert not (out / "skills").exists()

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "skills:" not in config_yaml and "read_skill" not in config_yaml

    config_py = (pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "SkillsConfig" not in config_py

    prompts_py = (pkg / "harness" / "prompts.py").read_text(encoding="utf-8")
    assert "skill" not in prompts_py.lower()


def test_skills_enabled_generates_support(tmp_path, spec):
    spec.skills.enabled = True
    out = tmp_path / "skills"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    assert (pkg / "harness" / "skills.py").is_file()
    assert (out / "tests" / "test_skills.py").is_file()
    assert (out / "skills" / "example-skill" / "SKILL.md").is_file()

    config_py = (pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "class SkillsConfig" in config_py and "skills: SkillsConfig" in config_py

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "skills:" in config_yaml and 'dirs: ["skills"]' in config_yaml
    assert "read_skill" in config_yaml  # the L2 tool is allowlisted on by default

    prompts_py = (pkg / "harness" / "prompts.py").read_text(encoding="utf-8")
    assert "build_skills_prompt" in prompts_py

    # skills.py is valid Python and the spec snapshot only records the enable flag
    py_compile.compile(str(pkg / "harness" / "skills.py"), doraise=True)
    snapshot = (out / "harness.spec.yaml").read_text(encoding="utf-8")
    assert "enabled: true" in snapshot
    assert "dirs" not in snapshot  # dirs is a runtime knob, not in the spec


# --- Slice 8B: cross-session long-term memory (opt-in, memory.enabled) -------


def test_memory_disabled_omits_footprint(tmp_path, preset_spec):
    """Default (memory.enabled=false) repo has zero memory footprint — and the
    core modules touched by memory render byte-for-byte as without it (gated)."""
    out = tmp_path / "nomem"
    generate(preset_spec, out, git_init=False)
    pkg = out / "src" / "coding_assistant"
    assert not (pkg / "harness" / "memory.py").exists()
    assert not (out / "tests" / "test_memory.py").exists()

    config_py = (pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "MemoryConfig" not in config_py

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "memory:" not in config_yaml
    assert "memory_read" not in config_yaml and "memory_append" not in config_yaml

    prompts_py = (pkg / "harness" / "prompts.py").read_text(encoding="utf-8")
    assert "memory" not in prompts_py.lower()

    # the loop core (context + paradigms) carries none of the memory wiring.
    # (``config`` flows into fit/generate unconditionally now — it is core wiring
    # for overflow rescue + fallback, not memory — so the memory footprint is just
    # the compact_rescue hook, gated off here.)
    context_py = (pkg / "harness" / "context.py").read_text(encoding="utf-8")
    assert "compact_rescue" not in context_py
    agent_py = (pkg / "harness" / "paradigms" / "agent.py").read_text(encoding="utf-8")
    assert "from ..memory" not in agent_py and "compact_rescue" not in agent_py

    cli_py = (pkg / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert "_setup_memory" not in cli_py and "def memory(" not in cli_py


def test_memory_enabled_generates_support(tmp_path, spec):
    spec.memory.enabled = True
    out = tmp_path / "mem"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    assert (pkg / "harness" / "memory.py").is_file()
    assert (out / "tests" / "test_memory.py").is_file()

    config_py = (pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "class MemoryConfig" in config_py and "memory: MemoryConfig" in config_py

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "memory:" in config_yaml and "backend: file" in config_yaml
    assert "memory_read" in config_yaml and "memory_append" in config_yaml

    prompts_py = (pkg / "harness" / "prompts.py").read_text(encoding="utf-8")
    assert "memory_section" in prompts_py

    # memory wires into the loop core + interfaces, all gated on this flag
    context_py = (pkg / "harness" / "context.py").read_text(encoding="utf-8")
    assert "compact_rescue" in context_py
    agent_py = (pkg / "harness" / "paradigms" / "agent.py").read_text(encoding="utf-8")
    assert "config=config" in agent_py
    cli_py = (pkg / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert "_setup_memory" in cli_py and "def memory(" in cli_py

    # memory.py is valid Python and the snapshot only records the enable flag
    py_compile.compile(str(pkg / "harness" / "memory.py"), doraise=True)
    snapshot = (out / "harness.spec.yaml").read_text(encoding="utf-8")
    assert "memory" in snapshot and "enabled: true" in snapshot


def test_memory_web_panel_present_when_enabled(tmp_path, spec):
    """memory + web on => the config page has a Memory tab, the memory tools are
    grouped as built-in (not "your tools"), and the backend endpoints are wired."""
    spec.memory.enabled = True
    spec.interfaces.web = True
    out = tmp_path / "memweb"
    generate(spec, out, git_init=False)
    base = out / "src" / "agent_harness" / "interfaces"
    idx = (base / "web_index.html").read_text(encoding="utf-8")
    web_py = (base / "web.py").read_text(encoding="utf-8")

    assert 'data-cfg="memory"' in idx and "subtab_memory" in idx
    assert "cfg-mem-consolidate" in idx and "cfg-mem-policy" in idx
    # Q1: memory_* are listed among BUILTIN_TOOLS so they group under "Built-in"
    assert '"memory_read", "memory_append", "memory_write"' in idx
    # the dedicated memory-manager role shows up in the Roles dropdown
    assert "role_memory" in idx and '"memory"' in idx
    assert "/memory/consolidate" in web_py and '"memory",' in web_py


def test_memory_web_footprint_absent_when_disabled(tmp_path, spec):
    """memory off + web on => the web UI/API carry zero memory wiring."""
    spec.memory.enabled = False
    spec.interfaces.web = True
    out = tmp_path / "webnomem"
    generate(spec, out, git_init=False)
    base = out / "src" / "agent_harness" / "interfaces"
    idx = (base / "web_index.html").read_text(encoding="utf-8")
    web_py = (base / "web.py").read_text(encoding="utf-8")

    assert 'data-cfg="memory"' not in idx and "subtab_memory" not in idx
    assert "memory_read" not in idx and "role_memory" not in idx
    assert "/memory" not in web_py and "memory" not in web_py.lower()


# --- One-click launch scripts (HarnessSmith / <display name>) ---------------


@pytest.mark.parametrize(
    "display_name, project_slug, expected",
    [
        ("My Coding Assistant", "agent_harness", "My Coding Assistant"),  # spaces kept
        ('Bad:/\\<>|?*"Name', "agent_harness", "Bad_________Name"),  # illegal -> _
        (None, "agent_harness", "agent_harness"),  # no display name -> slug
        ("   ", "fallback_slug", "fallback_slug"),  # blank -> slug
        ("...", "fallback_slug", "fallback_slug"),  # only dots -> slug
        ("ends with dot.", "fallback_slug", "ends with dot"),  # trailing dot trimmed
        ("CON", "fallback_slug", "fallback_slug"),  # reserved device name -> slug
        ("con.bat", "fallback_slug", "fallback_slug"),  # reserved + ext -> slug
        ("Über Bot", "fallback_slug", "Über Bot"),  # non-ASCII preserved
    ],
)
def test_launch_script_stem_sanitizes(display_name, project_slug, expected):
    from harnessmith.spec import HarnessSpec

    spec = HarnessSpec(project_slug=project_slug, display_name=display_name)
    assert launch_script_stem(spec) == expected


def test_launch_scripts_generated_with_exec_bit(tmp_path, spec):
    """Every product ships <name>.sh + <name>.bat; the .sh is executable."""
    import os
    import stat

    out = tmp_path / "launch"
    generate(spec, out, git_init=False)
    sh = out / "agent_harness.sh"  # example spec has no display_name -> slug
    bat = out / "agent_harness.bat"
    assert sh.is_file() and bat.is_file()
    # The exec bit only exists on POSIX filesystems (NTFS has none); on Windows the
    # generator's chmod is a no-op, so only assert it where it's meaningful.
    if os.name == "posix":
        assert sh.stat().st_mode & stat.S_IXUSR, "launch .sh must be executable"
    # no unrendered Jinja survived into the shell scripts
    for path in (sh, bat):
        text = path.read_text(encoding="utf-8")
        assert "{{" not in text and "{%" not in text, path
    # Windows .bat ships CRLF; .sh stays LF-only (correct on any host).
    bat_bytes = bat.read_bytes()
    assert b"\r\n" in bat_bytes and bat_bytes.replace(b"\r\n", b"").count(b"\n") == 0
    assert b"\r\n" not in sh.read_bytes()


def test_launch_script_name_follows_display_name(tmp_path, spec):
    """A display name with spaces/illegal chars yields a safe matching filename."""
    spec.display_name = "My: Assistant"
    out = tmp_path / "named"
    generate(spec, out, git_init=False)
    assert (out / "My_ Assistant.sh").is_file()
    assert (out / "My_ Assistant.bat").is_file()


def test_launch_scripts_bootstrap_uv_when_missing(tmp_path, spec):
    """When uv (and the console command) are absent, the launcher offers to
    install uv — winget first, then the official installer — so a fresh Windows
    box needs nothing preinstalled."""
    out = tmp_path / "bootstrap"
    generate(spec, out, git_init=False)
    sh = (out / "agent_harness.sh").read_text(encoding="utf-8")
    bat = (out / "agent_harness.bat").read_text(encoding="utf-8")
    # install choice prompt + the installed-command fallback are in both
    assert "Choose [1/2/n]" in sh and "Choose [1/2/n]" in bat
    # Windows: winget (signed) first, official installer as fallback; uv located
    # at its known install path since a fresh PATH isn't visible this session
    assert "astral-sh.uv" in bat and "astral.sh/uv/install.ps1" in bat
    assert r"%USERPROFILE%\.local\bin\uv.exe" in bat
    # POSIX: the official shell installer
    assert "astral.sh/uv/install.sh" in sh
    # China-mirror fallback (option 2): pip + Tsinghua mirror, run via the system
    # Python with uv's own mirror env vars so `uv run` doesn't hit GitHub either.
    for text in (sh, bat):
        assert "pypi.tuna.tsinghua.edu.cn" in text
        assert "UV_DEFAULT_INDEX" in text and "UV_PYTHON_PREFERENCE" in text
        assert "only-system" in text and "-m uv run" in text
    # Guard against the recursion that spammed "maximum setlocal recursion level"
    # on real cmd.exe: the .bat must stay a flat goto-based script (no setlocal,
    # no call-based subroutines), ending via the built-in :eof label.
    low = bat.lower()
    assert "setlocal" not in low and "call :" not in low
    assert "goto :eof" in low
    # Progress logging so the window isn't a silent black box, and a pause so it
    # doesn't vanish before the user can read it.
    assert "Step 1/4" in bat and "Launching:" in bat and "Process exited" in bat
    assert "pause" in low


def test_launch_scripts_auto_pick_china_mirror(tmp_path, spec):
    """With uv already present, the launchers auto-pick the index: probe the
    official PyPI (via curl) and fall back to the Tsinghua mirror when it's
    unreachable — no menu — while an explicit UV_DEFAULT_INDEX still wins."""
    out = tmp_path / "automirror"
    generate(spec, out, git_init=False)
    sh = (out / "agent_harness.sh").read_text(encoding="utf-8")
    bat = (out / "agent_harness.bat").read_text(encoding="utf-8")
    for text in (sh, bat):
        assert "pypi.org/simple/" in text  # probes the official index
        assert "curl" in text  # only probes when curl is available
        assert "unreachable" in text  # the mirror-fallback notice
        assert "pypi.tuna.tsinghua.edu.cn" in text  # the fallback mirror
        assert "UV_DEFAULT_INDEX" in text
    # Both launchers populate the system proxy so the curl probe goes the same way as
    # uv (curl ignores the WinINET/macOS GUI proxy on its own); without it the probe
    # could wrongly report PyPI unreachable behind a corporate proxy and pin a mirror.
    assert "Internet Settings" in bat  # Windows WinINET registry proxy
    assert "scutil --proxy" in sh  # macOS GUI proxy


def test_launch_node_bootstrap_only_when_a_node_server_is_prefilled(tmp_path):
    """The launcher offers a user-local portable Node ONLY when a Node-based MCP
    server (npx, e.g. desktop-commander) is prefilled — uvx-only prefills ride uv
    and get no Node logic. Node is fetched on demand, never bundled in the repo."""
    from harnessmith.catalog import resolve_servers

    spec = load_spec(preset_spec_path("coding-assistant"))
    stem = launch_script_stem(spec)

    # desktop-commander (npx) prefilled -> Node bootstrap present in both scripts.
    with_dc = tmp_path / "with_dc"
    generate(spec, with_dc, git_init=False, mcp_servers=preset_mcp_servers("coding-assistant"))
    sh = (with_dc / f"{stem}.sh").read_text(encoding="utf-8")
    bat = (with_dc / f"{stem}.bat").read_text(encoding="utf-8")
    for text in (sh, bat):
        assert "Node.js" in text
        assert "nodejs.org/dist" in text and "npmmirror.com/mirrors/node" in text
        assert "v22.11.0" in text  # pinned portable LTS
        assert "Choose [1/2/n]" in text  # official / China mirror / skip menu
    assert "ensure_node" in sh
    assert ":hf_node_ok" in bat
    low = bat.lower()  # must stay a flat goto script (the recursion footgun guard)
    assert "setlocal" not in low and "call :" not in low

    # uvx-only prefill (fetch) -> no Node logic at all (uv already covers it).
    uvx_only = tmp_path / "uvx_only"
    generate(spec, uvx_only, git_init=False, mcp_servers=resolve_servers(["fetch"]))
    for ext in ("sh", "bat"):
        text = (uvx_only / f"{stem}.{ext}").read_text(encoding="utf-8")
        assert "ensure_node" not in text and "nodejs.org/dist" not in text


def test_mcp_product_has_package_fetch_resolver_and_warm(tmp_path):
    """An MCP product carries the registry/proxy auto-resolver, the `mcp warm`
    command + config knobs; a no-MCP product carries none of it (zero footprint)."""
    spec = load_spec(preset_spec_path("coding-assistant"))
    out = tmp_path / "mcp_on"
    generate(spec, out, git_init=False, mcp_servers=preset_mcp_servers("coding-assistant"))
    pkg = spec.project_slug

    mcp_py = (out / "src" / pkg / "harness" / "mcp.py").read_text(encoding="utf-8")
    assert "_stdio_net_env" in mcp_py and "prewarm_stdio_packages" in mcp_py
    assert "_discover_proxy" in mcp_py and "getproxies" in mcp_py

    config_py = (out / "src" / pkg / "harness" / "config.py").read_text(encoding="utf-8")
    assert "npm_registry" in config_py and "pip_index" in config_py and "proxy:" in config_py

    cli_py = (out / "src" / pkg / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert 'mcp_app.command("warm")' in cli_py

    # The launch scripts reuse the system proxy (helps uv sync + npx alike).
    bat = (out / f"{launch_script_stem(spec)}.bat").read_text(encoding="utf-8")
    assert "Using system proxy" in bat

    # No-MCP product: none of the MCP machinery is generated.
    off = tmp_path / "mcp_off"
    spec.mcp.enabled = False
    generate(spec, off, git_init=False)
    assert not (off / "src" / pkg / "harness" / "mcp.py").exists()
    cli_off = (off / "src" / pkg / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert 'mcp_app.command("warm")' not in cli_off


def test_launch_bat_echo_safe_for_metachar_display_name(tmp_path):
    """A display name with cmd metacharacters (& < > |) must never reach an
    `echo` line — it would break batch parsing. The echoes use project_slug
    (always [a-z0-9_]); the raw display name lives only in REM comments."""
    from harnessmith.spec import HarnessSpec

    spec = HarnessSpec(
        project_slug="agent_harness", display_name="A & B <c> | d"
    )
    import re

    out = tmp_path / "meta"
    generate(spec, out, git_init=False)
    bat = (out / f"{launch_script_stem(spec)}.bat").read_text(encoding="utf-8")
    for line in bat.splitlines():
        if line.lstrip().lower().startswith("echo"):
            # ^-escaped metachars (e.g. the `^|` in the install hint) are fine;
            # only a BARE & < > | would break cmd parsing.
            unescaped = re.sub(r"\^.", "", line)
            assert not any(ch in unescaped for ch in "&<>|"), f"unsafe echo: {line!r}"


def test_launch_bat_fallback_uses_exe_to_avoid_self_shadow(tmp_path, spec):
    """The console-command fallback must target `<name>.exe`, never the bare
    name. On Windows a bare `agent_harness` / `harnessmith` resolves to the
    sibling .bat first (cwd is searched before PATH, case-insensitively), which
    relaunches the launcher forever."""
    # Product launcher: the default example has stem == slug == agent_harness,
    # so the .bat and the command share a name — the exact collision case.
    out = tmp_path / "shadow"
    generate(spec, out, git_init=False)
    bat = (out / "agent_harness.bat").read_text(encoding="utf-8")
    assert "where agent_harness.exe" in bat
    assert "agent_harness.exe %ACTION%" in bat
    assert "where agent_harness >nul" not in bat  # bare would match the .bat
    assert "\nagent_harness %ACTION%" not in bat

    # Generator launcher at the repo root (HarnessSmith.bat vs harnessmith).
    root_bat = (
        Path(__file__).resolve().parents[1] / "HarnessSmith.bat"
    ).read_text(encoding="utf-8")
    assert "where harnessmith.exe" in root_bat
    assert "harnessmith.exe wizard --open" in root_bat
    assert "\nharnessmith wizard --open" not in root_bat  # no bare relaunch


def test_root_launchers_offer_web_and_cli_setup():
    """The repo-root one-click launchers let the user choose the web form or the
    interactive CLI wizard (the CLI path is what makes headless Linux usable)."""
    root = Path(__file__).resolve().parents[1]
    sh = (root / "HarnessSmith.sh").read_text(encoding="utf-8")
    bat = (root / "HarnessSmith.bat").read_text(encoding="utf-8")

    # A mode prompt with both options is presented in each launcher.
    assert "choose_mode" in sh and "CLI wizard" in sh and "Web wizard" in sh
    assert "Choose [1/2]" in sh and "Choose [1/2]" in bat
    assert "CLI wizard" in bat and "Web wizard" in bat

    # The CLI branch routes to `harnessmith new` (the interactive wizard); the web
    # branch keeps the existing `wizard --open` form. The .bat keeps the `.exe`
    # console fallback so it never relaunches itself.
    assert "run harnessmith new" in sh  # via `"$uv_bin" run` / `harnessmith new`
    assert "uv run harnessmith new" in bat
    assert "harnessmith.exe new" in bat
    assert "run --extra wizard harnessmith wizard --open" in sh

    # Flat goto in the .bat (the Windows fragility guard from Slice 7): no setlocal,
    # no `call :` subroutines.
    assert "setlocal" not in bat.lower()
    assert "call :" not in bat


def test_launch_script_no_web_runs_chat(tmp_path, spec):
    """Without web, the one-click script launches the terminal chat REPL."""
    out = tmp_path / "chatlaunch"
    generate(spec, out, git_init=False)
    sh = (out / "agent_harness.sh").read_text(encoding="utf-8")
    bat = (out / "agent_harness.bat").read_text(encoding="utf-8")
    assert "action=(chat)" in sh and "serve --open" not in sh
    assert 'set "ACTION=chat"' in bat and "serve --open" not in bat


def test_launch_script_web_runs_serve_open(tmp_path, spec):
    """With web on, the one-click script starts serve + opens the browser."""
    spec.interfaces.web = True
    out = tmp_path / "weblaunch"
    generate(spec, out, git_init=False)
    sh = (out / "agent_harness.sh").read_text(encoding="utf-8")
    bat = (out / "agent_harness.bat").read_text(encoding="utf-8")
    assert "action=(serve --open)" in sh
    assert 'set "ACTION=serve --open"' in bat
    # the serve command grew an --open flag for the script to use
    cli = (out / "src" / "agent_harness" / "interfaces" / "cli.py").read_text(encoding="utf-8")
    assert "--open/--no-open" in cli and "_open_browser_when_ready" in cli


# --- Slice 12: native Anthropic dual-spec (built into every product) --------


def test_default_product_ships_dual_protocol(tmp_path, spec):
    """Every product carries both clients (human decision 2026-06-11): the
    anthropic module + dependency are always present, config.yaml spells out the
    default ``provider: openai``, and the panel offers the switch."""
    spec.interfaces.web = True
    out = tmp_path / "dualproto"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    assert (pkg / "harness" / "llm_anthropic.py").is_file()
    assert (out / "tests" / "test_llm_anthropic.py").is_file()
    assert "anthropic>=" in (out / "pyproject.toml").read_text(encoding="utf-8")
    # config.yaml makes the default explicit so users can see what to change
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "provider: openai" in config_yaml
    # the spec snapshot still keeps the default implicit (byte-stable old specs)
    assert "provider" not in (out / "harness.spec.yaml").read_text(encoding="utf-8")
    # the /config panel always offers the provider dropdown
    html = (pkg / "interfaces" / "web_index.html").read_text(encoding="utf-8")
    assert "p-provider" in html
    assert 'provOpt("anthropic")' in html
    assert 'o.provider = g("p-provider")' in html


def test_anthropic_profile_generates_client_dep_and_config(tmp_path, spec):
    from harnessmith.spec import LLMProfile

    spec.llms.append(
        LLMProfile(
            name="claude",
            model="claude-opus-4-8",
            provider="anthropic",
            api_key_env="ANTHROPIC_API_KEY",
        )
    )
    out = tmp_path / "anthropic"
    generate(spec, out, git_init=False)
    pkg = out / "src" / "agent_harness"

    module = pkg / "harness" / "llm_anthropic.py"
    assert module.is_file()
    assert (out / "tests" / "test_llm_anthropic.py").is_file()
    py_compile.compile(str(module), doraise=True)
    py_compile.compile(str(out / "tests" / "test_llm_anthropic.py"), doraise=True)

    pyproject = (out / "pyproject.toml").read_text(encoding="utf-8")
    assert "anthropic" in pyproject
    lowered = pyproject.lower()
    for forbidden in ("langchain", "langgraph", "adk"):
        assert forbidden not in lowered  # the SDK is an API client, not a framework

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "provider: anthropic" in config_yaml
    assert (
        "ANTHROPIC_API_KEY=" in (out / ".env.example").read_text(encoding="utf-8")
    )  # env NAME only

    # the snapshot records the opt-in and round-trips back into a valid spec
    snapshot = (out / "harness.spec.yaml").read_text(encoding="utf-8")
    assert "provider: anthropic" in snapshot
    reloaded = load_spec(out / "harness.spec.yaml")
    assert reloaded.llms[-1].provider == "anthropic"
    # the default profile stays implicit (openai is never written out)
    assert "provider: openai" not in snapshot
