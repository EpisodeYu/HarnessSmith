"""Golden-path end-to-end tests (slow; require uv + network, some require Docker).

Run them explicitly::

    uv run pytest -m golden
    uv run pytest -m "golden and docker"

They are excluded from the default run (see pyproject ``addopts``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from harnessforge.generator import (
    REQUIREMENTS_NAME,
    generate,
    lock_dependencies,
    smoke_check,
)
from harnessforge.presets import preset_spec_path
from harnessforge.spec import load_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("langchain", "langgraph", "adk")


@pytest.mark.golden
def test_golden_preset_generates_locks_and_smoke_passes(tmp_path):
    """preset -> generate -> uv lock -> uv sync + import + mock step + pytest."""
    spec = load_spec(preset_spec_path("coding-assistant"))
    out = tmp_path / "ca"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    assert (out / "uv.lock").is_file()
    requirements = out / REQUIREMENTS_NAME
    assert requirements.is_file()

    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    req_text = requirements.read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"
        assert forbidden not in req_text, f"{forbidden} in requirements.txt"

    # Raises SmokeCheckError on any failure (runs the generated pytest + a mock turn).
    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_web_enabled_generates_locks_and_smoke_passes(tmp_path):
    """web=true -> generate -> lock -> sync + import + mock step + pytest (test_web)."""
    spec = load_spec(preset_spec_path("coding-assistant"))
    spec.interfaces.web = True
    out = tmp_path / "ca_web"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    assert "fastapi" in lock_text and "uvicorn" in lock_text
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    # Runs the generated pytest, which includes tests/test_web.py (SSE + /config).
    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_uvx_harnessforge_new_smoke(tmp_path):
    """`uvx --from <repo> harnessforge new ...` builds + runs the CLI one-shot."""
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")
    out = tmp_path / "uvx_out"
    proc = subprocess.run(
        [
            "uvx", "--from", str(REPO_ROOT), "harnessforge", "new", str(out),
            "--preset", "coding-assistant", "--no-git", "--no-verify",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "pyproject.toml").is_file()
    assert (out / "uv.lock").is_file()
    assert (out / "src" / "coding_assistant" / "harness" / "loop.py").is_file()


@pytest.mark.golden
@pytest.mark.docker
def test_docker_build_and_run_mock_step(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    spec = load_spec(preset_spec_path("coding-assistant"))
    out = tmp_path / "ca"
    generate(spec, out, git_init=False)
    lock_dependencies(out)

    tag = "harnessforge_golden_smoke"
    build = subprocess.run(
        ["docker", "build", "-t", tag, str(out)], capture_output=True, text=True
    )
    assert build.returncode == 0, build.stdout + build.stderr
    try:
        run = subprocess.run(
            ["docker", "run", "--rm", tag], capture_output=True, text=True
        )
        assert run.returncode == 0, run.stdout + run.stderr
        assert "mock" in run.stdout.lower()
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, text=True)
