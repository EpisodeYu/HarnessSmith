"""FastAPI app for the spec wizard (Slice 7).

Routes:

- ``GET /``          — the single-page form (no build; Tailwind CDN + vanilla JS).
- ``GET /meta``      — field metadata the form needs (paradigms, built-in tools,
  MCP catalog, presets).
- ``POST /spec``     — validate the form via :class:`HarnessSpec`; return spec
  YAML + the matching ``harnessmith new`` command, or field-level errors.
- ``POST /generate`` — render the spec into an owned repo (the same ``generate()``
  the CLI uses). With ``launch: true`` (and a Web-enabled spec) it kicks off a
  background ``uv sync`` + ``uv run <slug> serve`` and returns a ``job_id``;
  otherwise it stays render-only (the user runs ``uv sync`` after, or relays via
  ``harnessmith new --spec``).
- ``GET /generate/status/{job_id}`` — poll a launch job's step-by-step progress
  (render -> sync -> serve); the product URL appears once the job is ``done``.

Secrets are never collected or returned — only env-var NAMES. This module imports
FastAPI, so it is only imported on demand (the ``harnessmith wizard`` command),
keeping the core CLI / ``uvx harnessmith new`` free of the wizard dependencies.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from ..catalog import CatalogError, load_catalog, resolve_servers
from ..skills_catalog import SkillCatalogError, load_skills_catalog, resolve_skills
from ..debuglog import log as debug_log, setup as setup_debug_log
from ..generator import TargetExistsError, generate
from ..node_bootstrap import ensure_portable_node, node_on_path
from ..presets import available_presets
from ..scaffold import (
    GENERATE_CONFIRM as _GENERATE_CONFIRM,
    PARADIGMS,
    WIZARD_CATALOG_DEFAULT as _WIZARD_CATALOG_DEFAULT,
    WIZARD_CATALOG_ORDER as _WIZARD_CATALOG_ORDER,
    WIZARD_SKILLS_DEFAULT as _WIZARD_SKILLS_DEFAULT,
    WIZARD_SKILLS_ORDER as _WIZARD_SKILLS_ORDER,
    apply_web_prefs as _apply_web_prefs,
    with_default_tools as _with_default_tools,
    with_defaults as _with_defaults,
)
from ..spec import HarnessSpec

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_HTML = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

# HarnessSmith repo root (wizard/app.py -> wizard -> harnessmith -> root). The
# one-click form prefills its target dir under ``<root>/generate/<project_slug>``
# (gitignored), so a quick local generate lands somewhere obvious.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATE_BASE = _REPO_ROOT / "generate"

# Structural-only baking, catalog curation, and the wizard HITL policy are shared
# with the interactive CLI wizard — they live in ``harnessmith.scaffold`` (which
# does NOT import FastAPI, so the core CLI can reuse them). Imported above as
# PARADIGMS / _WIZARD_CATALOG_ORDER / _WIZARD_CATALOG_DEFAULT / _GENERATE_CONFIRM /
# _with_defaults / _with_default_tools.

# Background product servers launched by the one-click "generate" flow. Held so
# the Popen handles (and their log file objects) aren't garbage-collected; the
# processes are detached (own session) and outlive the wizard on purpose.
_LAUNCHED: list[subprocess.Popen] = []

# In-flight one-click launch jobs (job id -> progress dict), polled by the UI to
# drive a step-by-step progress bar. The product becomes openable only once the
# job is ``done``. Single-user local dev tool, so a plain dict is enough.
_JOBS: dict[str, dict] = {}
# Ordered launch steps the UI renders. ``render`` is finished before the job is
# created (generate() ran synchronously); ``sync``/``serve`` run in a worker.
_LAUNCH_STEPS = ("render", "sync", "serve")

def _spec_yaml(spec: HarnessSpec) -> str:
    """Serialize a validated spec to YAML (env-var NAMES only; never secrets)."""
    data = spec.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _format_errors(exc: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in err["loc"]), "msg": err["msg"]}
        for err in exc.errors()
    ]


def _catalog_meta() -> list[dict]:
    """Catalog servers the wizard surfaces: curated order + default-checked flag."""
    catalog = load_catalog()
    servers = []
    for name in _WIZARD_CATALOG_ORDER:
        s = catalog.get(name)
        if s is None:
            continue
        servers.append(
            {
                "name": s.name,
                "description": s.description,
                "transport": s.transport,
                "requires": s.requires,
                "default_checked": name in _WIZARD_CATALOG_DEFAULT,
                "tools": [
                    {"name": t.name, "risk": t.risk, "default_enabled": t.default_enabled}
                    for t in s.tools
                ],
            }
        )
    return servers


def _skills_catalog_meta() -> list[dict]:
    """Bundled skills the wizard surfaces: curated order + default-checked flag."""
    catalog = load_skills_catalog()
    skills = []
    for name in _WIZARD_SKILLS_ORDER:
        s = catalog.get(name)
        if s is None:
            continue
        skills.append(
            {
                "name": s.name,
                "description": s.description,
                "default_checked": name in _WIZARD_SKILLS_DEFAULT,
            }
        )
    return skills


def _find_free_port(preferred: int = 8000, host: str = "127.0.0.1") -> int:
    """Return a bindable port: try ``preferred`` upward, else an OS-assigned one."""
    for candidate in range(preferred, preferred + 64):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _wait_port(host: str, port: int, *, timeout: float = 300.0) -> bool:
    """Block until ``host:port`` accepts a TCP connection (or ``timeout`` elapses)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(1)
    return False


# Backstop for the product's first ``uv sync`` — it may download a managed Python
# plus a handful of wheels, which behind a slow/firewalled network legitimately
# takes many minutes. Set deliberately generous so a slow-but-working install is
# never killed (the UI shows uv's live output + elapsed time, so the user sees it
# progressing); this only bounds a *truly* wedged process from leaking forever.
_UV_SYNC_TIMEOUT = 1800.0


# Tsinghua's PyPI mirror — the same trusted, university-run mirror the launcher's
# China-install path uses. Only an *index* mirror (wheels/sdists); it deliberately
# does NOT touch managed-Python downloads (those would need a separate, untrusted
# GitHub proxy — out of bounds per the supply-chain rule in CLAUDE.md).
_CN_PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

# Env keys that already pin an index; if any is set we never override the choice.
_INDEX_ENV_KEYS = ("UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_INDEX", "PIP_INDEX_URL")

# Probe result, cached for the process (probing twice — sync then serve — is
# pointless and the reachability of PyPI won't flip mid-launch).
_index_probe_cached: bool | None = None


def _pypi_reachable(url: str = "https://pypi.org/simple/", timeout: float = 3.0) -> bool:
    """True if the official PyPI answers a quick HEAD within ``timeout``.

    Any HTTP response (even an error status) counts as reachable — only a
    connection failure / timeout (the GFW-blocked case) counts as unreachable."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def _auto_index() -> str | None:
    """The China-mirror index URL to fall back to, or ``None`` to keep the default.

    Picks the mirror only when the official PyPI looks unreachable (e.g. behind
    the GFW). Cached so the (up-to-``timeout``) probe runs at most once."""
    global _index_probe_cached
    if _index_probe_cached is None:
        _index_probe_cached = _pypi_reachable()
    return None if _index_probe_cached else _CN_PYPI_MIRROR


def _ensure_proxy_env(env: dict[str, str]) -> None:
    """Fill HTTP(S)_PROXY from the system proxy (Windows/macOS settings) when the
    environment doesn't already set one, so the product's ``uv sync`` and its
    ``npx``/``uvx`` MCP servers reach the network through a corporate proxy.

    The product's own MCP bridge also auto-detects the proxy, but ``uv sync`` runs
    here (before the product starts), so it needs the env set too."""
    if any(env.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")):
        return
    proxies = urllib.request.getproxies()
    proxy = proxies.get("https") or proxies.get("http")
    if proxy:
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = env["https_proxy"] = proxy


def _resolve_index(index_url: str | None = None) -> tuple[str, str]:
    """Resolve the package index that the product's ``uv`` calls will use, plus a
    short human reason — for *display/logging only* (the actual env wiring lives in
    :func:`_product_env`, which is kept behavior-identical when no explicit index is
    given). Precedence, highest first:

    - ``index_url`` — an explicit choice made in the wizard this run (the new knob);
    - an index already pinned in the environment (e.g. ``UV_DEFAULT_INDEX`` the
      launcher set behind the GFW) — left exactly as-is;
    - auto: the China mirror when official PyPI looks unreachable, else PyPI's default.

    Returns ``(label, reason)`` where ``label`` is the index URL (or the literal
    ``"official PyPI"`` when uv is left on its built-in default)."""
    explicit = (index_url or "").strip()
    if explicit:
        return explicit, "explicit"
    for key in _INDEX_ENV_KEYS:
        pinned = os.environ.get(key)
        if pinned:
            return pinned, "env-pinned"
    mirror = _auto_index()
    if mirror:
        return mirror, "auto-mirror"
    return "official PyPI", "auto-official"


def _product_env(index_url: str | None = None) -> dict[str, str]:
    """Environment for the product's own ``uv`` invocations.

    The wizard is itself launched by ``uv run`` *inside HarnessSmith's venv*,
    which exports ``VIRTUAL_ENV`` (and sometimes ``UV_PROJECT_ENVIRONMENT``)
    pointing at that venv. Inherited unchanged, the product's ``uv sync`` /
    ``uv run`` would target the wizard's environment instead of the product's
    own ``.venv`` — and on Windows, where files in an in-use venv are locked,
    that means fighting the still-running parent, so the sync never finishes.
    Dropping those keys lets uv resolve the product's own ``.venv``.

    Index selection: an explicit ``index_url`` (the wizard's optional knob) always
    wins; otherwise behavior is unchanged — a pinned index (e.g. one the launcher
    set via ``UV_DEFAULT_INDEX``) is preserved, and only when none is pinned *and*
    official PyPI looks unreachable is a China mirror filled in.
    """
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    _ensure_proxy_env(env)
    explicit = (index_url or "").strip()
    if explicit:
        env["UV_DEFAULT_INDEX"] = explicit
    elif not any(env.get(k) for k in _INDEX_ENV_KEYS):
        mirror = _auto_index()
        if mirror:
            env["UV_DEFAULT_INDEX"] = mirror
    return env


def _log_text(path: Path) -> str:
    """Full log contents, or ``""`` if it can't be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _log_tail(path: Path, lines: int = 3) -> str:
    """Last few non-empty log lines, joined into a single-line status hint."""
    text = _log_text(path)
    kept = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " | ".join(kept[-lines:])


def _run_uv(
    args: list[str], *, cwd: Path, log, index_url: str | None = None, extra_path: str | None = None
) -> int:
    """Run a ``uv`` subcommand, streaming combined output to the open ``log`` handle.

    ``extra_path`` (e.g. a provisioned portable Node's bin dir) is prepended to the
    child's PATH so a ``uv run <slug> mcp warm`` can launch its ``npx`` servers.
    Returns the exit code; a timeout maps to 124 (after killing the child) so the
    caller reports a failure instead of leaving the UI spinning forever."""
    env = _product_env(index_url)
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
    try:
        return subprocess.run(  # noqa: S603 — local dev convenience, fixed argv
            ["uv", *args],
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=_UV_SYNC_TIMEOUT,
        ).returncode
    except subprocess.TimeoutExpired:
        log.write(
            f"\n[harnessmith] `uv {' '.join(args)}` did not finish within "
            f"{int(_UV_SYNC_TIMEOUT)}s and was aborted — the package index or a "
            "managed-Python download is likely unreachable (behind a firewall, "
            "try a mirror).\n"
        )
        return 124


def _looks_like_cache_corruption(log_text: str) -> bool:
    """True if ``log_text`` shows a uv *cache* access failure (Windows ``os error 5``).

    uv's global distribution cache can be left half-written or locked — by an
    earlier interrupted/partially-removed install, or antivirus holding a temp
    file — which surfaces as "failed to rename ... os error 5" / "拒绝访问" when
    uv tries to finalise a cache entry. Gated on a permission-denied marker so a
    plain network/index failure never triggers the (heavier) cache wipe."""
    low = log_text.lower()
    denied = any(m in low for m in ("os error 5", "拒绝访问", "access is denied"))
    if not denied:
        return False
    return "distribution cache" in low or "failed to rename" in low


def _uv_sync(target_dir: Path, *, index_url: str | None = None) -> tuple[int, str]:
    """Run ``uv sync`` in the generated repo (installs deps).

    Returns ``(exit_code, log_tail)``; output is captured to ``<target>/.setup.log``
    for troubleshooting. The first log line records which package index this run
    actually uses (explicit knob / env-pinned / auto) so a slow or failed install is
    diagnosable after the fact.

    Self-heals the common Windows failure mode where a stale/partially-removed
    entry in uv's global cache makes the install abort with ``os error 5``
    ("拒绝访问"): on that specific signature, clean the cache once and retry the
    sync — the same ``uv cache clean`` users run by hand to get unstuck."""
    log_path = target_dir / ".setup.log"
    with log_path.open("w", encoding="utf-8") as log:
        index_label, index_reason = _resolve_index(index_url)
        log.write(f"[harnessmith] package index: {index_label} ({index_reason})\n")
        log.flush()
        code = _run_uv(["sync"], cwd=target_dir, log=log, index_url=index_url)
        if code != 0:
            log.flush()
            if _looks_like_cache_corruption(_log_text(log_path)):
                log.write(
                    "\n[harnessmith] uv sync failed with a cache access error "
                    "(os error 5 / 拒绝访问) — this usually means a stale or "
                    "partially-removed entry in uv's global cache. Running "
                    "`uv cache clean` and retrying the sync once...\n"
                )
                log.flush()
                _run_uv(["cache", "clean"], cwd=target_dir, log=log, index_url=index_url)
                code = _run_uv(["sync"], cwd=target_dir, log=log, index_url=index_url)
    return code, _log_tail(log_path)


def _launch_product(
    target_dir: Path,
    project_slug: str,
    port: int,
    *,
    host: str = "127.0.0.1",
    extra_path: str | None = None,
    index_url: str | None = None,
) -> None:
    """Spawn ``uv run <slug> serve`` in the background (detached, own session).

    Output goes to ``<target>/.serve.log`` and the process outlives the wizard on
    purpose. ``extra_path`` (e.g. a provisioned portable Node's bin dir) is prepended
    to the child's PATH so its ``npx``-based MCP servers can launch. Set the LLM key
    in the product's config page / .env to actually chat.
    """
    env = _product_env(index_url)
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
    log = (target_dir / ".serve.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(  # noqa: S603 — local dev convenience, fixed argv
        ["uv", "run", project_slug, "serve", "--host", host, "--port", str(port)],
        cwd=str(target_dir),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    _LAUNCHED.append(proc)


def _job_steps(needs_node: bool, needs_warm: bool = False) -> tuple[str, ...]:
    """Ordered launch steps: render -> sync -> [node] -> [warm] -> serve.

    ``node`` is inserted only when a Node-based MCP server is prefilled (it provisions
    a portable Node first). ``warm`` is inserted when ANY stdio MCP server is prefilled:
    it pre-fetches their npx/uvx packages ONCE (a one-time cold download, slow on a
    first run / behind the GFW) as its OWN clearly-labelled step — so ``serve`` is then
    a fast bind (the product's serve sees the warm sentinel and skips its own warm)
    instead of conflating that minutes-long download into "starting the web"."""
    steps = ["render", "sync"]
    if needs_node:
        steps.append("node")
    if needs_warm:
        steps.append("warm")
    steps.append("serve")
    return tuple(steps)


def _new_job(needs_node: bool = False, needs_warm: bool = False) -> dict:
    """A fresh launch-progress record (``render`` already done by generate())."""
    return {
        "id": uuid.uuid4().hex,
        "steps": [
            {"key": k, "status": "done" if k == "render" else "pending"}
            for k in _job_steps(needs_node, needs_warm)
        ],
        "url": None,
        "done": False,
        "error": None,
    }


def _set_step(job: dict, key: str, status: str) -> None:
    debug_log.debug("wizard: launch job %s step %s -> %s", job["id"], key, status)
    for step in job["steps"]:
        if step["key"] == key:
            step["status"] = status


def _run_launch(
    job: dict,
    target_dir: Path,
    project_slug: str,
    *,
    host: str = "127.0.0.1",
    index_url: str | None = None,
    serve_timeout: float = 300.0,
) -> None:
    """Worker: ``uv sync`` then start serve, updating ``job`` step-by-step.

    ``serve_timeout`` is how long to wait for the web port to open — scaled up by the
    caller when stdio MCP servers are prefilled, since the first ``serve`` foreground-
    warms their packages before binding (see :func:`_job_steps`)."""
    try:
        # Expose the sync log so the status endpoint can stream uv's live output
        # (the install can be slow behind a firewall; without this the UI looks
        # frozen during the quiet download phase).
        job["setup_log"] = str(target_dir / ".setup.log")
        _set_step(job, "sync", "running")
        code, log_tail = _uv_sync(target_dir, index_url=index_url)
        if code != 0:
            _set_step(job, "sync", "error")
            hint = f" Last log: {log_tail}" if log_tail else ""
            job["error"] = f"uv sync failed (see {target_dir / '.setup.log'})." + hint
            return
        _set_step(job, "sync", "done")

        # A Node-based MCP server (e.g. Desktop Commander via npx) needs a Node
        # runtime, which the headless `uv run serve` below won't get from the
        # launch scripts. Provision a user-local portable Node (best-effort) and
        # prepend it to the product's PATH so npx works. The step streams its own
        # log so a slow ~30MB download reads as progressing, not frozen.
        node_path: str | None = None
        if any(s["key"] == "node" for s in job["steps"]):
            _set_step(job, "node", "running")
            node_log = target_dir / ".node.log"
            job["setup_log"] = str(node_log)
            if node_on_path():
                _set_step(job, "node", "done")
            else:
                with node_log.open("w", encoding="utf-8") as nlog:
                    # Behind the GFW (PyPI unreachable) nodejs.org is usually
                    # reachable-but-throttled, so try the domestic mirror first.
                    node_path = ensure_portable_node(
                        project_slug, prefer_mirror=not _pypi_reachable(), log=nlog
                    )
                _set_step(job, "node", "done")

        # Prepare MCP tools: pre-fetch the stdio MCP packages (npx/uvx) ONCE here,
        # with per-server progress, as a step of its OWN — so the long cold download
        # isn't hidden inside "start web". It writes the warm sentinel, so the serve
        # step below binds instantly (the product's serve skips its own warm). Best-
        # effort: a server that can't warm is failure-isolated on the product's MCP
        # page later, so the launch proceeds to serve regardless of the exit code.
        if any(s["key"] == "warm" for s in job["steps"]):
            _set_step(job, "warm", "running")
            warm_log = target_dir / ".warm.log"
            job["setup_log"] = str(warm_log)
            with warm_log.open("w", encoding="utf-8") as wlog:
                _run_uv(
                    ["run", project_slug, "mcp", "warm"],
                    cwd=target_dir, log=wlog, index_url=index_url, extra_path=node_path,
                )
            _set_step(job, "warm", "done")

        _set_step(job, "serve", "running")
        job["setup_log"] = str(target_dir / ".serve.log")  # stream serve output too
        port = _find_free_port()
        _launch_product(
            target_dir, project_slug, port, host=host, extra_path=node_path, index_url=index_url
        )
        if _wait_port(host, port, timeout=serve_timeout):
            job["url"] = f"http://{host}:{port}"
            _set_step(job, "serve", "done")
            job["done"] = True
        else:
            _set_step(job, "serve", "error")
            job["error"] = "the product web did not become reachable in time"
    except Exception as exc:  # never leave a step stuck on "running"
        debug_log.debug("wizard: launch job %s crashed", job["id"], exc_info=True)
        for step in job["steps"]:
            if step["status"] == "running":
                step["status"] = "error"
        job["error"] = str(exc)
    if job.get("error"):
        debug_log.debug("wizard: launch job %s error: %s", job["id"], job["error"])


def _spawn_launch(
    job: dict,
    target_dir: Path,
    project_slug: str,
    *,
    index_url: str | None = None,
    serve_timeout: float = 300.0,
) -> None:
    """Start :func:`_run_launch` on a daemon thread (overridable in tests)."""
    threading.Thread(
        target=_run_launch,
        args=(job, target_dir, project_slug),
        kwargs={"index_url": index_url, "serve_timeout": serve_timeout},
        daemon=True,
    ).start()


def _resolve_prefill(spec: HarnessSpec, names: list[str]):
    """Resolve catalog selections (only when mcp.enabled); raises CatalogError."""
    if spec.mcp.enabled and names:
        return [_with_default_tools(s) for s in resolve_servers([str(n) for n in names])]
    return []


def _resolve_skills_prefill(spec: HarnessSpec, names):
    """Resolve bundled-skill selections (only when skills.enabled); raises
    SkillCatalogError. ``names is None`` (client didn't send a list) falls back to
    the recommended default set, mirroring the wizard's default-checked box."""
    if not spec.skills.enabled:
        return []
    if names is None:
        names = sorted(_WIZARD_SKILLS_DEFAULT)
    return resolve_skills([str(n) for n in names])


def _spec_from_body(body: dict) -> HarnessSpec:
    """Validate the posted spec, applying the soft web-tool preference hint when a
    key-based upgrade server (Bocha / Jina) is prefilled — the web twin of the CLI
    wizard's ``build_spec``. Raises ``ValidationError`` on bad input (handled by the
    callers, exactly as before)."""
    raw = dict(body.get("spec") or {})
    prepared = _with_defaults(raw)
    if (raw.get("mcp") or {}).get("enabled"):
        prepared = _apply_web_prefs(prepared, body.get("mcp_servers") or [])
    return HarnessSpec.model_validate(prepared)


def create_app() -> FastAPI:
    setup_debug_log()  # covered by the CLI path too; direct uvicorn use gets it here
    app = FastAPI(title="HarnessSmith wizard")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    @app.get("/meta")
    def meta() -> dict:
        return {
            "paradigms": PARADIGMS,
            "catalog": _catalog_meta(),
            "skills_catalog": _skills_catalog_meta(),
            "presets": available_presets(),
            "generate_base": str(_GENERATE_BASE),
            # When the wizard runs on Linux the user may be accessing it over an
            # SSH tunnel from another OS, so the UI surfaces a port-forward hint
            # for the launched product. (On Windows/macOS it's local — no hint.)
            "linux": sys.platform.startswith("linux"),
        }

    @app.post("/spec")
    async def post_spec(request: Request):
        body = await request.json()
        try:
            spec = _spec_from_body(body)
        except ValidationError as exc:
            return JSONResponse({"ok": False, "errors": _format_errors(exc)}, status_code=400)
        try:
            servers = _resolve_prefill(spec, body.get("mcp_servers") or [])
        except CatalogError as exc:
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "mcp_servers", "msg": str(exc)}]},
                status_code=400,
            )
        try:
            skills = _resolve_skills_prefill(spec, body.get("skills"))
        except SkillCatalogError as exc:
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "skills", "msg": str(exc)}]},
                status_code=400,
            )
        target = str(body.get("target_dir") or "").strip() or "<target-dir>"
        cmd = (
            f"harnessmith new {target} --spec spec.yaml"
            + "".join(f" --mcp-server {s.name}" for s in servers)
            + "".join(f" --skill {s.name}" for s in skills)
        )
        return {"ok": True, "yaml": _spec_yaml(spec), "new_command": cmd}

    @app.post("/generate")
    async def post_generate(request: Request):
        body = await request.json()
        target_dir = str(body.get("target_dir") or "").strip()
        if not target_dir:
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "target_dir", "msg": "target_dir is required"}]},
                status_code=400,
            )
        try:
            spec = _spec_from_body(body)
        except ValidationError as exc:
            debug_log.debug("wizard: /generate spec invalid: %s", exc)
            return JSONResponse({"ok": False, "errors": _format_errors(exc)}, status_code=400)
        try:
            servers = _resolve_prefill(spec, body.get("mcp_servers") or [])
        except CatalogError as exc:
            debug_log.debug("wizard: /generate mcp prefill invalid: %s", exc)
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "mcp_servers", "msg": str(exc)}]},
                status_code=400,
            )
        try:
            skills = _resolve_skills_prefill(spec, body.get("skills"))
        except SkillCatalogError as exc:
            debug_log.debug("wizard: /generate skill prefill invalid: %s", exc)
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "skills", "msg": str(exc)}]},
                status_code=400,
            )
        debug_log.debug(
            "wizard: /generate slug=%s target=%s launch=%s servers=%s skills=%s",
            spec.project_slug, target_dir, bool(body.get("launch")),
            [s.name for s in servers], [s.name for s in skills],
        )
        try:
            result = generate(
                spec,
                target_dir,
                git_init=bool(body.get("git", False)),
                mcp_servers=servers,
                skills=skills,
                confirm_default=_GENERATE_CONFIRM,
            )
        except TargetExistsError as exc:
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "target_dir", "msg": str(exc)}]},
                status_code=400,
            )
        resp = {
            "ok": True,
            "target_dir": str(result.target_dir),
            "project_slug": result.project_slug,
            "files": len(result.written_files),
            "next": (
                f"cd {result.target_dir} && uv sync && "
                f'uv run {result.project_slug} run --mock "hello"'
            ),
        }
        # One-click launch: kick off uv sync + serve on a worker and hand back a
        # job id; the UI polls /generate/status to drive a step-by-step progress
        # bar and only opens the product once the job is done. Only meaningful
        # when the Web interface was generated; render-only otherwise.
        if body.get("launch") and spec.interfaces.web:
            needs_node = any(
                s.requires == "node" or (s.command or "").lower() in {"npx", "npm", "node"}
                for s in servers
            )
            # Optional per-run package index override (empty -> keep the automatic
            # behavior). Lets a user behind a slow corporate proxy point uv at a
            # mirror the proxy can actually reach fast, instead of the auto pick.
            index_url = str(body.get("index_url") or "").strip() or None
            # First-run `serve` foreground-warms each stdio MCP package (npx/uvx)
            # before binding the port — a one-time cold download capped per server in
            # the product (~120s each, sequential). Scale the web-reachability wait to
            # the prefilled stdio-server count so a slow first warm isn't misreported
            # as "did not become reachable"; a server-less project keeps the 300s base.
            stdio_count = sum(1 for s in servers if (s.command or "").strip())
            serve_timeout = max(300.0, 150.0 * stdio_count)
            # Any stdio MCP server -> a dedicated "warm" step pre-fetches its packages
            # before serve (so serve binds instantly; see _job_steps).
            job = _new_job(needs_node, needs_warm=stdio_count > 0)
            _JOBS[job["id"]] = job
            _spawn_launch(
                job, Path(result.target_dir), result.project_slug,
                index_url=index_url, serve_timeout=serve_timeout,
            )
            resp["job_id"] = job["id"]
        return resp

    @app.get("/generate/status/{job_id}")
    def generate_status(job_id: str):
        job = _JOBS.get(job_id)
        if job is None:
            return JSONResponse({"error": "unknown job"}, status_code=404)
        # Tack on uv's latest output (read live from the log) so the UI can show
        # the install progressing instead of looking frozen. Never mutates the job.
        setup_log = job.get("setup_log")
        if setup_log:
            return {**job, "log_tail": _log_tail(Path(setup_log), lines=4)}
        return job

    return app


app = create_app()
