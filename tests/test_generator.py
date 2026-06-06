"""Generator / rendering tests (Slice 0 + Slice 1 templates).

These are fast: they render templates and inspect output without running uv,
network, or Docker. End-to-end runnability lives in ``test_golden.py``.
"""

from __future__ import annotations

import py_compile
from pathlib import Path

import pytest
import yaml

from harnessforge.generator import TargetExistsError, generate
from harnessforge.presets import preset_mcp_servers, preset_spec_path
from harnessforge.spec import load_spec

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
    assert (out / ".python-version").read_text().strip() == "3.11"


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
    assert "max_steps: 8" in config
    assert "sk-" not in config  # never a real secret value


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

    config_py = (out / "src" / "coding_assistant" / "harness" / "config.py").read_text()
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
    loop = (out / "src" / "coding_assistant" / "harness" / "loop.py").read_text()
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
    assert 'id="lang"' in idx and "中文" in idx  # language switch (en/zh)
    assert 'id="cfg-tabs"' in idx  # config is paged by function
    for sub in (
        "subtab_llm", "subtab_context", "subtab_budget", "subtab_tools",
        "subtab_prompts", "subtab_paradigms", "subtab_observability",
    ):
        assert sub in idx


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
    """The baseline prefill lands fetch/git/DC in config.yaml with the right
    default allowlist (fetch + git-read on, mutating git + DC off)."""
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
    disabled = {t["name"] for t in config["tools"] if not t["enabled"]}
    assert "fetch__fetch" in enabled
    assert "ddg-search__search" in enabled and "ddg-search__fetch_content" in enabled
    assert "git__git_status" in enabled and "git__git_log" in enabled
    assert "git__git_commit" in disabled and "git__git_add" in disabled
    # Desktop Commander predefined but every tool default OFF (one-click enable)
    assert any(n.startswith("desktop-commander__") for n in disabled)
    assert not any(n.startswith("desktop-commander__") for n in enabled)


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
    from harnessforge.catalog import resolve_servers

    out = tmp_path / "nomcp"
    generate(spec, out, git_init=False, mcp_servers=resolve_servers(["fetch"]))
    config_yaml = (out / "config.yaml").read_text(encoding="utf-8").lower()
    assert "mcp" not in config_yaml
    assert "fetch__fetch" not in config_yaml


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
