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

from harnessmith.generator import (
    REQUIREMENTS_NAME,
    generate,
    lock_dependencies,
    prewarm_mcp_servers,
    smoke_check,
)
from harnessmith.presets import preset_mcp_servers, preset_spec_path
from harnessmith.spec import load_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SPEC = REPO_ROOT / "examples" / "spec.yaml"
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
    assert "ruamel" in lock_text  # comment-preserving /config write-back dep
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    # Runs the generated pytest, which includes tests/test_web.py (SSE + /config).
    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_mcp_enabled_generates_locks_and_smoke_passes(tmp_path):
    """mcp=true -> generate -> lock -> sync + import + mock step + pytest (test_mcp).

    The generated test_mcp.py spins up a local stdio MCP server (no network, no
    key) and exercises discovery + a real tool call + allowlist filtering.
    """
    spec = load_spec(preset_spec_path("coding-assistant"))
    spec.mcp.enabled = True
    out = tmp_path / "ca_mcp"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    assert "name = \"mcp\"" in lock_text or "mcp" in lock_text
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    # Runs the generated pytest, which includes tests/test_mcp.py (stdio + allowlist).
    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_multi_paradigm_generates_locks_and_smoke_passes(tmp_path):
    """paradigms=[agent,plan,ask] -> generate -> lock -> sync + import + mock step
    + pytest (each paradigm exercised by the generated test_harness)."""
    spec = load_spec(preset_spec_path("coding-assistant"))
    spec.paradigms = ["agent", "plan", "ask"]
    out = tmp_path / "ca_paradigms"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    pdir = out / "src" / result.project_slug / "harness" / "paradigms"
    for name in ("__init__", "agent", "plan", "ask"):
        assert (pdir / f"{name}.py").is_file(), name

    # Runs the generated pytest, including the plan/ask + custom-paradigm tests.
    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_thin_example_stays_thin_and_smoke_passes(tmp_path):
    """The plain example spec (no MCP) is the thin anchor: no mcp dep, smoke green."""
    spec = load_spec(EXAMPLE_SPEC)
    out = tmp_path / "thin"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    assert 'name = "mcp"' not in lock_text  # stays thin: no MCP dependency
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_mcp_baseline_prefill_smoke(tmp_path):
    """coding-assistant baseline: prefill fetch/git/DC into config.yaml (each
    enabled by a `<server>__*` wildcard), prewarm the uvx servers, then smoke.
    fetch+git launch (their tools are enabled); DC needs Node so it's skipped."""
    spec = load_spec(preset_spec_path("coding-assistant"))
    servers = preset_mcp_servers("coding-assistant")
    out = tmp_path / "ca_baseline"
    # git_init=False on purpose: the git server is NOT pinned to --repository, so it
    # must stay healthy even when the cwd is not a git repo (regression: pinning made
    # mcp-server-git exit at startup -> "unreachable: Connection closed").
    result = generate(spec, out, git_init=False, mcp_servers=servers)

    config_yaml = (out / "config.yaml").read_text(encoding="utf-8")
    assert "fetch__*" in config_yaml and "mcp-server-git" in config_yaml
    assert "--repository" not in config_yaml  # not pinned -> healthy in any cwd

    lock_dependencies(out)
    prewarm_mcp_servers(servers)  # warm uvx cache so the smoke launch is fast

    # The git server connects from a non-repo cwd (its health reflects the tool, not
    # the cwd). `mcp status` prints "unreachable: <err>" for a server that didn't come
    # up; git must not be among them.
    status = subprocess.run(
        ["uv", "run", "--quiet", result.project_slug, "mcp", "status"],
        cwd=out, capture_output=True, text=True, timeout=300,
    )
    git_lines = [ln for ln in status.stdout.splitlines() if "git " in ln and "[stdio]" in ln]
    assert git_lines, status.stdout + status.stderr
    assert "unreachable" not in git_lines[0], status.stdout + status.stderr

    # smoke runs `<pkg> run --mock` which starts fetch+git; a slow/failing server
    # is skipped (connect timeout + failure isolation), never hangs the run.
    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_skills_enabled_generates_and_smoke_passes(tmp_path):
    """skills.enabled -> generate -> lock -> sync + import + mock step + pytest
    (the generated test_skills.py + a mock turn that discovers the example skill)."""
    spec = load_spec(EXAMPLE_SPEC)
    spec.skills.enabled = True
    out = tmp_path / "skills"
    result = generate(spec, out, git_init=False)

    assert (out / "skills" / "example-skill" / "SKILL.md").is_file()
    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_memory_enabled_generates_and_smoke_passes(tmp_path):
    """memory.enabled -> generate -> lock -> sync + import + mock step + pytest
    (the generated test_memory.py: file backend, injection, tools, a mock turn
    that writes a note, the no-secrets guarantee, and a custom @register_memory)."""
    spec = load_spec(EXAMPLE_SPEC)
    spec.memory.enabled = True
    out = tmp_path / "memory"
    result = generate(spec, out, git_init=False)

    assert (out / "src" / result.project_slug / "harness" / "memory.py").is_file()
    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_golden_wizard_spec_generates_and_smoke_passes(tmp_path):
    """The wizard's POST /spec output is a real spec: validate -> generate ->
    lock -> sync + import + mock step + pytest (web=true, so test_web runs)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from harnessmith.wizard.app import create_app

    client = TestClient(create_app())
    # Structural-only form (what the slimmed wizard sends): the backend bakes the
    # behavioral defaults (llms/prompts/tools) that make it runnable.
    spec_data = {
        "display_name": "Wizard Bot",
        "project_slug": "wizard_bot",
        "language": "zh",
        "paradigms": ["agent", "plan", "ask"],
        "interfaces": {"cli": True, "web": True},
        "mcp": {"enabled": False},
        "skills": {"enabled": False},
        "memory": {"enabled": True},  # checked by default in the wizard form
    }
    resp = client.post("/spec", json={"spec": spec_data})
    assert resp.status_code == 200, resp.text
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(resp.json()["yaml"], encoding="utf-8")

    spec = load_spec(spec_file)
    out = tmp_path / "wizard_out"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    assert "fastapi" in lock_text  # web=true -> web deps locked in
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, forbidden

    smoke_check(out, result.project_slug)


@pytest.mark.golden
def test_uvx_harnessmith_new_smoke(tmp_path):
    """`uvx --from <repo> harnessmith new ...` builds + runs the CLI one-shot."""
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")
    out = tmp_path / "uvx_out"
    proc = subprocess.run(
        [
            "uvx", "--from", str(REPO_ROOT), "harnessmith", "new", str(out),
            "--preset", "coding-assistant", "--no-git", "--no-verify", "--no-prewarm",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "pyproject.toml").is_file()
    assert (out / "uv.lock").is_file()
    assert (out / "src" / "coding_assistant" / "harness" / "loop.py").is_file()
    # The CLI applied the preset's MCP prefill into the runtime config.
    assert "fetch__*" in (out / "config.yaml").read_text(encoding="utf-8")


@pytest.mark.golden
@pytest.mark.docker
def test_docker_build_and_run_mock_step(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    spec = load_spec(preset_spec_path("coding-assistant"))
    out = tmp_path / "ca"
    generate(spec, out, git_init=False)
    lock_dependencies(out)

    tag = "harnessmith_golden_smoke"
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


@pytest.mark.golden
@pytest.mark.docker
def test_docker_mcp_baseline_bakes_and_runs_offline(tmp_path):
    """The MCP baseline bakes uvx servers into the image so a no-network
    `docker run` still boots (servers launch from the warmed cache; mock step)."""
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    spec = load_spec(preset_spec_path("coding-assistant"))
    servers = preset_mcp_servers("coding-assistant")
    out = tmp_path / "ca_mcp_docker"
    generate(spec, out, git_init=False, mcp_servers=servers)
    lock_dependencies(out)

    dockerfile = (out / "Dockerfile").read_text(encoding="utf-8")
    assert "uvx mcp-server-fetch --help" in dockerfile and "UV_OFFLINE=1" in dockerfile

    tag = "harnessmith_golden_mcp_baseline"
    build = subprocess.run(
        ["docker", "build", "-t", tag, str(out)], capture_output=True, text=True
    )
    assert build.returncode == 0, build.stdout + build.stderr
    try:
        # --network none proves the baked image runs with zero network.
        run = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", tag],
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        assert "mock" in run.stdout.lower()
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, text=True)


@pytest.mark.golden
def test_golden_anthropic_profile_generates_locks_and_smoke_passes(tmp_path):
    """provider=anthropic -> generate -> lock -> sync + import + mock step +
    pytest (incl. tests/test_llm_anthropic.py: mapping + stream assembly)."""
    from harnessmith.spec import LLMProfile

    spec = load_spec(preset_spec_path("coding-assistant"))
    spec.llms.append(
        LLMProfile(
            name="claude",
            model="claude-opus-4-8",
            provider="anthropic",
            api_key_env="ANTHROPIC_API_KEY",
        )
    )
    out = tmp_path / "ca_anthropic"
    result = generate(spec, out, git_init=False)

    lock_dependencies(out)
    lock_text = (out / "uv.lock").read_text(encoding="utf-8").lower()
    assert "anthropic" in lock_text  # the SDK is locked in
    for forbidden in FORBIDDEN:
        assert forbidden not in lock_text, f"{forbidden} in uv.lock"

    # Runs the generated pytest, which includes tests/test_llm_anthropic.py.
    smoke_check(out, result.project_slug)
