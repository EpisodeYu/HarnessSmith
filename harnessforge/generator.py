"""Render a HarnessSpec into a standalone, owned repo (Slice 0).

Pipeline: load spec -> render ``templates/`` with Jinja2 -> write the repo ->
drop a secret-safe ``harness.spec.yaml`` snapshot -> ``git init``. Re-running
against a non-empty target is refused (we never overwrite a user's repo).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .spec import HarnessSpec, load_spec

TEMPLATES_DIR = Path(__file__).parent / "templates"
PATH_SLUG_TOKEN = "__project_slug__"
JINJA_SUFFIX = ".j2"
SPEC_SNAPSHOT_NAME = "harness.spec.yaml"


class GenerationError(Exception):
    """Base class for generation failures."""


class TargetExistsError(GenerationError):
    """Raised when the target directory already exists and is not empty."""


@dataclass
class GenerationResult:
    target_dir: Path
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

    result = GenerationResult(target_dir=target_dir)
    for template_file in _iter_template_files(templates_dir):
        relpath = template_file.relative_to(templates_dir)
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
