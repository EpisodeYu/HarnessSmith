"""Render a HarnessSpec into a standalone, owned repo, then make it runnable.

Pipeline: load spec -> render ``templates/`` with Jinja2 -> write the repo ->
drop a secret-safe ``harness.spec.yaml`` snapshot -> ``git init``. Slice 1 adds
runnability: ``uv lock`` (+ a ``requirements.txt`` export) and a post-generation
smoke check (``uv sync`` -> import -> mock step -> ``pytest``). Re-running against
a non-empty target is refused (we never overwrite a user's repo).
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .catalog import CatalogServer
from .spec import HarnessSpec, load_spec

TEMPLATES_DIR = Path(__file__).parent / "templates"
PATH_SLUG_TOKEN = "__project_slug__"
# Path token replaced by the product's launch-script base name (derived from the
# display name): e.g. ``__launch_name__.sh.j2`` -> ``My Coding Assistant.sh``.
LAUNCH_NAME_TOKEN = "__launch_name__"
JINJA_SUFFIX = ".j2"
SPEC_SNAPSHOT_NAME = "harness.spec.yaml"
REQUIREMENTS_NAME = "requirements.txt"

# Characters illegal in a Windows filename (the set also covers '/' on POSIX),
# plus ASCII control chars. Spaces are intentionally KEPT — the launch scripts
# quote them — so the script name can mirror the display name as closely as
# possible.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Reserved DOS device names: a file named like one (with or without an
# extension) is unusable on Windows, so we fall back to the slug.
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def launch_script_stem(spec: HarnessSpec) -> str:
    r"""Filesystem-safe base name for the product's one-click launch script.

    Derived from ``display_name`` (falling back to ``project_slug``): spaces and
    most characters are kept so the script name matches the display name, but
    characters illegal on Windows (``< > : " / \ | ? *`` + control chars) become
    ``_``, trailing dots/spaces are trimmed, and reserved DOS device names are
    rejected. Falls back to ``project_slug`` when nothing usable remains.
    """
    raw = (spec.display_name or spec.project_slug).strip()
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    base = cleaned.split(".", 1)[0].strip().upper()
    if not cleaned or base in _WINDOWS_RESERVED_NAMES:
        return spec.project_slug
    return cleaned

# Templates written only when their spec predicate is true. Keys are paths
# relative to ``templates/`` (posix, keeping the slug token and the .j2 suffix).
# This is how an opt-in capability stays out of a repo that didn't ask for it:
# the web interface now, MCP / wizard in later slices. Everything not listed
# here is always rendered.
CONDITIONAL_TEMPLATES: dict[str, Callable[[HarnessSpec], bool]] = {
    # Always-apply project rules (the AGENTS.md/CLAUDE.md/.cursor-rules pattern):
    # a starter RULES.md is generated only when the spec seeds it into
    # prompts.rules_files; otherwise the repo stays free of an unused rule file.
    "RULES.md.j2": lambda spec: "RULES.md" in spec.prompts.rules_files,
    "src/__project_slug__/interfaces/web.py.j2": lambda spec: spec.interfaces.web,
    "src/__project_slug__/interfaces/web_index.html.j2": lambda spec: spec.interfaces.web,
    "tests/test_web.py.j2": lambda spec: spec.interfaces.web,
    "src/__project_slug__/harness/mcp.py.j2": lambda spec: spec.mcp.enabled,
    "tests/test_mcp.py.j2": lambda spec: spec.mcp.enabled,
    "tests/_mcp_dummy_server.py.j2": lambda spec: spec.mcp.enabled,
    # Standard Agent Skills (Slice 6): skills.py + a sample skill + its test are
    # generated only when opted in; disabled leaves zero skills footprint.
    "src/__project_slug__/harness/skills.py.j2": lambda spec: spec.skills.enabled,
    "tests/test_skills.py.j2": lambda spec: spec.skills.enabled,
    "skills/example-skill/SKILL.md.j2": lambda spec: spec.skills.enabled,
    # Cross-session long-term memory (Slice 8B): the memory module + its test are
    # rendered only when opted in; disabled leaves zero memory footprint.
    "src/__project_slug__/harness/memory.py.j2": lambda spec: spec.memory.enabled,
    "tests/test_memory.py.j2": lambda spec: spec.memory.enabled,
    # Paradigms (Slice 5): the registry + agent are always rendered; the other
    # built-in paradigm files appear only when selected in spec.paradigms.
    "src/__project_slug__/harness/paradigms/plan.py.j2": lambda spec: "plan" in spec.paradigms,
    "src/__project_slug__/harness/paradigms/ask.py.j2": lambda spec: "ask" in spec.paradigms,
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


# Portable Node.js the product launcher offers to fetch when a Node-based MCP
# server (e.g. Desktop Commander via npx) is prefilled but Node isn't installed —
# Windows install rate is low, so the launcher bootstraps a user-local Node (not
# bundled in the repo). A pinned LTS keeps the download URL stable/offline-safe.
NODE_LTS_VERSION = "v22.11.0"


def _build_context(
    spec: HarnessSpec,
    mcp_servers: list[CatalogServer],
    confirm_default: str = "none",
) -> dict:
    """Build the Jinja render context from a spec (+ optional MCP prefill).

    ``mcp_servers`` is a generation-time convenience (catalog selections) that is
    rendered into the runtime ``config.yaml`` only when ``spec.mcp.enabled``. It
    never touches the spec/snapshot — servers are a runtime knob.

    ``confirm_default`` seeds the runtime ``confirm`` HITL policy in config.yaml
    (a runtime knob, not a spec field): ``none`` by default; the wizard passes
    ``high`` so its products gate high-risk tools (e.g. Desktop Commander) behind
    HITL confirmation.
    """
    env_names: list[str] = []
    for profile in spec.llms:
        for name in (profile.api_key_env, profile.base_url_env):
            if name and name not in env_names:
                env_names.append(name)

    servers = mcp_servers if (spec.mcp.enabled and mcp_servers) else []
    mcp_server_entries = [s.server_entry() for s in servers]
    mcp_tool_allowlist: list[dict] = []
    for s in servers:
        mcp_tool_allowlist.extend(s.allowlist_entries())
    # uvx-launched packages get prewarmed + baked into the Docker image so the
    # generated repo runs offline; Node-based servers are documented, not baked.
    mcp_uvx_packages: list[str] = []
    for s in servers:
        pkg = s.uvx_package
        if pkg and pkg not in mcp_uvx_packages:
            mcp_uvx_packages.append(pkg)
    # Does any prefilled server need Node (npx/node)? If so the launcher offers to
    # bootstrap a portable Node — uvx servers ride uv (already required), but a
    # Node server (Desktop Commander) has no runtime on a typical Windows box.
    mcp_needs_node = any(
        s.requires == "node" or (s.command or "").lower() in {"npx", "npm", "node"}
        for s in servers
    )

    return {
        "spec": spec,
        "version": spec.version,
        "project_slug": spec.project_slug,
        # Human-readable label for UI titles / README; slug is the fallback.
        "display_name": spec.display_name or spec.project_slug,
        # Filesystem-safe base name of the one-click launch script (so docs can
        # name the exact file). Mirrors the path-token substitution below.
        "launch_name": launch_script_stem(spec),
        # Baked-in default UI language for the product web ("en" | "zh").
        "language": spec.language,
        "llms": spec.llms,
        "roles": spec.roles,
        "interfaces": spec.interfaces,
        "tools": spec.tools,
        "paradigms": spec.paradigms,
        "observability": spec.observability,
        "env_names": env_names,
        "mcp_servers": mcp_server_entries,
        "mcp_tool_allowlist": mcp_tool_allowlist,
        "mcp_uvx_packages": mcp_uvx_packages,
        "mcp_needs_node": mcp_needs_node,
        "node_version": NODE_LTS_VERSION,
        "confirm_default": confirm_default,
    }


def _iter_template_files(templates_dir: Path) -> list[Path]:
    return sorted(p for p in templates_dir.rglob("*") if p.is_file())


def _render_relpath(relpath: Path, project_slug: str, launch_stem: str) -> Path:
    parts: list[str] = []
    for part in relpath.parts:
        if part == PATH_SLUG_TOKEN:
            parts.append(project_slug)
        elif LAUNCH_NAME_TOKEN in part:
            parts.append(part.replace(LAUNCH_NAME_TOKEN, launch_stem))
        else:
            parts.append(part)
    out = Path(*parts)
    if out.name.endswith(JINJA_SUFFIX):
        out = out.with_name(out.name[: -len(JINJA_SUFFIX)])
    return out


def _write_rendered(out_path: Path, rendered: str) -> None:
    """Write a rendered file with the right line endings + bits for its type.

    Windows ``.bat`` launchers ship CRLF (label/``goto`` parsing is happiest with
    it) regardless of the host the generator runs on; ``.sh`` launchers stay LF
    and get the executable bit so a double-click / ``./run`` works. Everything
    else keeps the platform default.
    """
    suffix = out_path.suffix
    if suffix == ".bat":
        text = rendered.replace("\r\n", "\n").replace("\n", "\r\n")
        out_path.write_text(text, encoding="utf-8", newline="")
    elif suffix == ".sh":
        out_path.write_text(rendered, encoding="utf-8", newline="")  # force LF
        out_path.chmod(out_path.stat().st_mode | 0o111)
    else:
        out_path.write_text(rendered, encoding="utf-8")


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
    mcp_servers: list[CatalogServer] | None = None,
    confirm_default: str = "none",
) -> GenerationResult:
    """Render ``spec`` into ``target_dir``.

    ``mcp_servers`` (catalog selections from ``--mcp-server`` / a preset prefill)
    are written into the generated ``config.yaml`` when ``spec.mcp.enabled``; they
    are a runtime knob, never added to the spec/snapshot. ``confirm_default`` seeds
    the runtime HITL ``confirm`` policy (``none`` default; the wizard passes
    ``high``) — also a runtime knob, not part of the spec.

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
    context = _build_context(spec, mcp_servers or [], confirm_default=confirm_default)

    launch_stem = launch_script_stem(spec)
    result = GenerationResult(target_dir=target_dir, project_slug=spec.project_slug)
    for template_file in _iter_template_files(templates_dir):
        relpath = template_file.relative_to(templates_dir)
        predicate = CONDITIONAL_TEMPLATES.get(relpath.as_posix())
        if predicate is not None and not predicate(spec):
            continue
        out_relpath = _render_relpath(relpath, spec.project_slug, launch_stem)
        rendered = env.get_template(relpath.as_posix()).render(**context)
        out_path = target_dir / out_relpath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_rendered(out_path, rendered)
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
    mcp_servers: list[CatalogServer] | None = None,
) -> GenerationResult:
    """Convenience: load a spec file then :func:`generate`."""
    return generate(
        load_spec(spec_path), target_dir, git_init=git_init, mcp_servers=mcp_servers
    )


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


PREWARM_TIMEOUT_SECONDS = 120


def prewarm_mcp_servers(servers: list[CatalogServer]) -> list[str]:
    """Warm the uv cache for uvx-based MCP servers so the first run is fast/offline.

    Best-effort: ``uvx <pkg> --help`` downloads + builds the ephemeral environment
    that the generated repo reuses at runtime (the same cache an offline ``uvx``
    falls back to). Failures (no network, a server without ``--help``) are
    swallowed — only successfully warmed names are returned — so scaffolding never
    fails here. Node-based servers are skipped (need Node; warmed on first use).
    """
    warmed: list[str] = []
    for server in servers:
        pkg = server.uvx_package
        if not pkg:
            continue
        try:
            subprocess.run(
                ["uvx", pkg, "--help"],
                cwd=Path.cwd(),
                check=True,
                capture_output=True,
                env=_clean_env(),
                timeout=PREWARM_TIMEOUT_SECONDS,
            )
            warmed.append(server.name)
        except (OSError, subprocess.SubprocessError):
            continue  # offline / unavailable — non-fatal (first run still works online)
    return warmed


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
