"""Render a HarnessSpec into a standalone, owned repo, then make it runnable.

Pipeline: load spec -> render ``templates/`` with Jinja2 -> write the repo ->
drop a secret-safe ``harness.spec.yaml`` snapshot -> ``git init``. Slice 1 adds
runnability: ``uv lock`` (+ a ``requirements.txt`` export) and a post-generation
smoke check (``uv sync`` -> import -> mock step -> ``pytest``). Re-running against
a non-empty target is refused (we never overwrite a user's repo).
"""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .spec import HarnessSpec, load_spec

TEMPLATES_DIR = Path(__file__).parent / "templates"
PATH_SLUG_TOKEN = "__project_slug__"
JINJA_SUFFIX = ".j2"
SPEC_SNAPSHOT_NAME = "harness.spec.yaml"
REQUIREMENTS_NAME = "requirements.txt"

# Templates written only when their spec predicate is true. Keys are paths
# relative to ``templates/`` (posix, keeping the slug token and the .j2 suffix).
# This is how an opt-in capability stays out of a repo that didn't ask for it:
# the web interface now, MCP / wizard in later slices. Everything not listed
# here is always rendered.
CONDITIONAL_TEMPLATES: dict[str, Callable[[HarnessSpec], bool]] = {
    "src/__project_slug__/interfaces/web.py.j2": lambda spec: spec.interfaces.web,
    "src/__project_slug__/interfaces/web_index.html.j2": lambda spec: spec.interfaces.web,
    "tests/test_web.py.j2": lambda spec: spec.interfaces.web,
}


class GenerationError(Exception):
    """Base class for generation failures."""


class TargetExistsError(GenerationError):
    """Raised when the target directory already exists and is not empty."""


class ToolingError(GenerationError):
    """Raised when an external tool (uv) is missing or a command fails."""


class SmokeCheckError(GenerationError):
    """Raised when the generated repo fails its post-generation smoke check."""


@dataclass
class GenerationResult:
    target_dir: Path
    project_slug: str = "agent_harness"
    written_files: list[Path] = field(default_factory=list)
    git_initialized: bool = False


def _build_context(spec: HarnessSpec) -> dict:
    """Build the Jinja render context from a spec."""
    env_names: list[str] = []
    for profile in spec.llms:
        for name in (profile.api_key_env, profile.base_url_env):
            if name and name not in env_names:
                env_names.append(name)
    return {
        "spec": spec,
        "version": spec.version,
        "project_slug": spec.project_slug,
        "llms": spec.llms,
        "roles": spec.roles,
        "interfaces": spec.interfaces,
        "tools": spec.tools,
        "observability": spec.observability,
        "env_names": env_names,
    }


def _iter_template_files(templates_dir: Path) -> list[Path]:
    return sorted(p for p in templates_dir.rglob("*") if p.is_file())


def _render_relpath(relpath: Path, project_slug: str) -> Path:
    parts = [
        project_slug if part == PATH_SLUG_TOKEN else part
        for part in relpath.parts
    ]
    out = Path(*parts)
    if out.name.endswith(JINJA_SUFFIX):
        out = out.with_name(out.name[: -len(JINJA_SUFFIX)])
    return out


def _spec_snapshot_yaml(spec: HarnessSpec) -> str:
    """Serialize the validated spec to YAML.

    Safe to commit: the spec only ever holds env-var *names*, never values.
    ``exclude_none`` keeps unused reserved fields out of the snapshot.
    """
    data = spec.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def generate(
    spec: HarnessSpec,
    target_dir: str | Path,
    *,
    templates_dir: Path = TEMPLATES_DIR,
    git_init: bool = True,
) -> GenerationResult:
    """Render ``spec`` into ``target_dir``.

    Refuses to write into a non-empty existing directory (raises
    :class:`TargetExistsError`) so an existing repo is never clobbered.
    """
    target_dir = Path(target_dir)
    if target_dir.exists() and any(target_dir.iterdir()):
        raise TargetExistsError(
            f"target directory {target_dir} already exists and is not empty; "
            "refusing to overwrite. Choose a new directory or remove it first."
        )

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        autoescape=False,
    )
    context = _build_context(spec)

    result = GenerationResult(target_dir=target_dir, project_slug=spec.project_slug)
    for template_file in _iter_template_files(templates_dir):
        relpath = template_file.relative_to(templates_dir)
        predicate = CONDITIONAL_TEMPLATES.get(relpath.as_posix())
        if predicate is not None and not predicate(spec):
            continue
        out_relpath = _render_relpath(relpath, spec.project_slug)
        rendered = env.get_template(relpath.as_posix()).render(**context)
        out_path = target_dir / out_relpath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        result.written_files.append(out_path)

    snapshot_path = target_dir / SPEC_SNAPSHOT_NAME
    snapshot_path.write_text(_spec_snapshot_yaml(spec), encoding="utf-8")
    result.written_files.append(snapshot_path)

    if git_init:
        result.git_initialized = _git_init(target_dir)

    return result


def _git_init(target_dir: Path) -> bool:
    try:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=target_dir,
            check=True,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def generate_from_spec_file(
    spec_path: str | Path,
    target_dir: str | Path,
    *,
    git_init: bool = True,
) -> GenerationResult:
    """Convenience: load a spec file then :func:`generate`."""
    return generate(load_spec(spec_path), target_dir, git_init=git_init)


# Env vars that would pin a *parent* virtualenv/project onto the child `uv`
# invocation. We must drop them so `uv` operates on the generated repo's own
# environment — otherwise running under `uv run`/`uvx harnessforge` (as in the
# smoke check) leaks the wrong interpreter into the new repo.
_VENV_ENV_VARS = (
    "VIRTUAL_ENV",
    "UV_PROJECT_ENV",
    "UV_PROJECT",
    "PYTHONHOME",
    "PYTHONPATH",
    "CONDA_PREFIX",
)


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in _VENV_ENV_VARS:
        env.pop(name, None)
    return env


def _run_uv(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a ``uv`` subcommand in ``cwd``, raising ToolingError on failure."""
    cmd = ["uv", *args]
    try:
        return subprocess.run(
            cmd, cwd=cwd, check=True, capture_output=True, text=True, env=_clean_env()
        )
    except FileNotFoundError as exc:
        raise ToolingError(
            "`uv` was not found on PATH. Install it from https://docs.astral.sh/uv/ "
            "(or re-run with --no-verify to skip the runnability check)."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ToolingError(
            f"command failed ({' '.join(cmd)}):\n"
            f"{(exc.stdout or '').strip()}\n{(exc.stderr or '').strip()}".strip()
        ) from exc


def lock_dependencies(repo: str | Path) -> None:
    """Resolve a cross-platform ``uv.lock`` and export ``requirements.txt``.

    The lock is generated (not templated) because the dependency set depends on
    the spec. ``requirements.txt`` is a pip fallback for users without uv.
    """
    repo = Path(repo)
    _run_uv(["lock"], repo)
    exported = _run_uv(
        ["export", "--format", "requirements-txt", "--no-hashes", "--no-emit-project"],
        repo,
    )
    (repo / REQUIREMENTS_NAME).write_text(exported.stdout, encoding="utf-8")


def smoke_check(repo: str | Path, project_slug: str) -> None:
    """Prove the generated repo runs: sync, import, a mock step, then pytest.

    Raises :class:`SmokeCheckError` with the underlying tool output on any
    failure so the caller can surface an actionable message.
    """
    repo = Path(repo)
    try:
        _run_uv(["sync", "--quiet"], repo)
        _run_uv(["run", "--quiet", "python", "-c", f"import {project_slug}"], repo)
        _run_uv(["run", "--quiet", project_slug, "run", "--mock", "smoke test"], repo)
        _run_uv(["run", "--quiet", "pytest", "-q"], repo)
    except ToolingError as exc:
        raise SmokeCheckError(str(exc)) from exc


@dataclass
class DoctorReport:
    uv_ok: bool
    uv_version: str | None
    network_ok: bool
    notes: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.uv_ok and self.network_ok


def doctor(*, network_host: str = "pypi.org", network_port: int = 443) -> DoctorReport:
    """Pre-flight check: is uv installed and is the package index reachable?"""
    notes: list[str] = []
    uv_version: str | None = None
    try:
        proc = subprocess.run(
            ["uv", "--version"], check=True, capture_output=True, text=True
        )
        uv_version = proc.stdout.strip()
        uv_ok = True
    except (OSError, subprocess.CalledProcessError):
        uv_ok = False
        notes.append("uv not found — install from https://docs.astral.sh/uv/")

    try:
        with socket.create_connection((network_host, network_port), timeout=5):
            network_ok = True
    except OSError:
        network_ok = False
        notes.append(
            f"cannot reach {network_host}:{network_port} — locking/sync need network "
            "(use --no-verify for offline scaffolding)."
        )

    return DoctorReport(
        uv_ok=uv_ok, uv_version=uv_version, network_ok=network_ok, notes=notes
    )
