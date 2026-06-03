"""Generator / rendering tests (Slice 0 + Slice 1 templates).

These are fast: they render templates and inspect output without running uv,
network, or Docker. End-to-end runnability lives in ``test_golden.py``.
"""

from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

from harnessforge.generator import TargetExistsError, generate
from harnessforge.presets import preset_spec_path
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
