"""Generator / rendering tests (Slice 0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from harnessforge.generator import TargetExistsError, generate
from harnessforge.spec import load_spec

EXAMPLE_SPEC = Path(__file__).resolve().parents[1] / "examples" / "spec.yaml"


@pytest.fixture
def spec():
    return load_spec(EXAMPLE_SPEC)


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
