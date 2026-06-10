"""FastAPI app for the spec wizard (Slice 7).

Routes:

- ``GET /``          — the single-page form (no build; Tailwind CDN + vanilla JS).
- ``GET /meta``      — field metadata the form needs (paradigms, built-in tools,
  MCP catalog, presets).
- ``POST /spec``     — validate the form via :class:`HarnessSpec`; return spec
  YAML + the matching ``harnessforge new`` command, or field-level errors.
- ``POST /generate`` — render the spec into an owned repo (the same ``generate()``
  the CLI uses). With ``launch: true`` (and a Web-enabled spec) it kicks off a
  background ``uv sync`` + ``uv run <slug> serve`` and returns a ``job_id``;
  otherwise it stays render-only (the user runs ``uv sync`` after, or relays via
  ``harnessforge new --spec``).
- ``GET /generate/status/{job_id}`` — poll a launch job's step-by-step progress
  (render -> sync -> serve); the product URL appears once the job is ``done``.

Secrets are never collected or returned — only env-var NAMES. This module imports
FastAPI, so it is only imported on demand (the ``harnessforge wizard`` command),
keeping the core CLI / ``uvx harnessforge new`` free of the wizard dependencies.
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
from dataclasses import replace
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from ..catalog import CatalogError, load_catalog, resolve_servers
from ..generator import TargetExistsError, generate
from ..node_bootstrap import ensure_portable_node, node_on_path
from ..presets import available_presets
from ..spec import HarnessSpec

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_HTML = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

# HarnessForge repo root (wizard/app.py -> wizard -> harnessforge -> root). The
# one-click form prefills its target dir under ``<root>/generate/<project_slug>``
# (gitignored), so a quick local generate lands somewhere obvious.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATE_BASE = _REPO_ROOT / "generate"

# The built-in loop paradigms (cf. spec.paradigms' Literal). agent is the default
# tool-calling loop; plan/ask are read-only.
PARADIGMS = [
    {"name": "agent", "description": "Default tool-calling loop (ReAct-style; self-corrects on tool errors)."},
    {"name": "plan", "description": "Read-only: investigates with low-risk tools and outputs a step-by-step plan."},
    {"name": "ask", "description": "Read-only: answers questions with low-risk tools; never mutates."},
]

# Which catalog servers the wizard surfaces, in display order, and which are
# checked by default. The catalog itself keeps every server (``--mcp-server``
# still resolves e.g. github/time) — this only curates the *form*. ``git`` is the
# practical local default (keyless, read tools on); ``github`` (needs a token, no
# enabled tools) and ``time`` (niche) are hidden here. Desktop Commander (shell +
# full filesystem) is default-ON in the wizard product — safety is the HITL
# confirmation gate (``confirm: high``, see ``_BAKED_DEFAULTS`` / ``_GENERATE_CONFIRM``),
# a deliberate, signed loosening of the "high-risk off by default" baseline for
# wizard products only (Slice 11). It still needs Node (npx) at runtime.
_WIZARD_CATALOG_ORDER = ("fetch", "ddg-search", "git", "desktop-commander")
_WIZARD_CATALOG_DEFAULT = frozenset({"fetch", "ddg-search", "git", "desktop-commander"})

# Catalog servers whose tools the wizard ships ENABLED by default (overriding the
# catalog's off-by-default state). Powerful but HITL-gated (``confirm: high``).
_WIZARD_TOOLS_ON = frozenset({"desktop-commander"})

# HITL confirmation policy seeded into a wizard product's config.yaml: every
# risk=high tool (shell / file writes / Desktop Commander) pauses for the user's
# OK before it runs. The CLI / preset paths keep the "none" default.
_GENERATE_CONFIRM = "high"

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

# Behavioral defaults baked into the spec when the (structural-only) wizard form
# omits them. The wizard intentionally hides these — a generator can produce many
# products, each configuring its own LLM / prompts / budget at runtime in the
# product's own config page / .env. Baking sensible defaults keeps the generated
# product complete and runnable out of the box. Secrets are env-var NAMES only.
# Only filled when absent/empty, so an explicit spec (or a hand-written one) wins.
_BAKED_DEFAULTS: dict = {
    # The LLM profile is scaffolded with the env-var NAMES but NO model: the
    # one-click wizard never asks which model, so guessing one (gpt-4o-mini) only
    # mis-fires on non-OpenAI providers. The generated product gates chat until
    # the user sets a model on its own config page (+ the key in .env).
    "llms": [
        {
            "name": "default",
            "model": "",
            "api_key_env": "OPENAI_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
        }
    ],
    "roles": {"generation": "default"},
    "prompts": {"system": "You are a helpful assistant."},
    "tools": [
        {"name": "get_current_time", "enabled": True},
        {"name": "calculator", "enabled": True},
    ],
    "budget": {"conditions": {"max_steps": 8}},
}


def _with_defaults(spec_data: dict) -> dict:
    """Fill behavioral defaults the structural-only wizard form omits."""
    out = dict(spec_data)
    for key, value in _BAKED_DEFAULTS.items():
        if not out.get(key):
            out[key] = value
    return out


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


def _product_env() -> dict[str, str]:
    """Environment for the product's own ``uv`` invocations.

    The wizard is itself launched by ``uv run`` *inside HarnessForge's venv*,
    which exports ``VIRTUAL_ENV`` (and sometimes ``UV_PROJECT_ENVIRONMENT``)
    pointing at that venv. Inherited unchanged, the product's ``uv sync`` /
    ``uv run`` would target the wizard's environment instead of the product's
    own ``.venv`` — and on Windows, where files in an in-use venv are locked,
    that means fighting the still-running parent, so the sync never finishes.
    Dropping those keys lets uv resolve the product's own ``.venv``.

    Index selection is automatic: an explicitly-configured index (e.g. a mirror
    the launcher set via ``UV_DEFAULT_INDEX``) is preserved; otherwise, when the
    official PyPI looks unreachable, a China mirror is filled in so the install
    can still fetch deps.
    """
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    _ensure_proxy_env(env)
    if not any(env.get(k) for k in _INDEX_ENV_KEYS):
        mirror = _auto_index()
        if mirror:
            env["UV_DEFAULT_INDEX"] = mirror
    return env


def _log_tail(path: Path, lines: int = 3) -> str:
    """Last few non-empty log lines, joined into a single-line status hint."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    kept = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " | ".join(kept[-lines:])


def _uv_sync(target_dir: Path) -> tuple[int, str]:
    """Run ``uv sync`` in the generated repo (installs deps).

    Returns ``(exit_code, log_tail)``; output is captured to ``<target>/.setup.log``
    for troubleshooting. A timeout maps to exit code 124 (after killing the child)
    so the caller reports a failure instead of leaving the UI spinning forever."""
    log_path = target_dir / ".setup.log"
    with log_path.open("w", encoding="utf-8") as log:
        try:
            code = subprocess.run(  # noqa: S603 — local dev convenience, fixed argv
                ["uv", "sync"],
                cwd=str(target_dir),
                stdout=log,
                stderr=subprocess.STDOUT,
                env=_product_env(),
                timeout=_UV_SYNC_TIMEOUT,
            ).returncode
        except subprocess.TimeoutExpired:
            log.write(
                f"\n[harnessforge] uv sync did not finish within {int(_UV_SYNC_TIMEOUT)}s "
                "and was aborted — the package index or a managed-Python download is "
                "likely unreachable (behind a firewall, try a mirror).\n"
            )
            code = 124
    return code, _log_tail(log_path)


def _launch_product(
    target_dir: Path,
    project_slug: str,
    port: int,
    *,
    host: str = "127.0.0.1",
    extra_path: str | None = None,
) -> None:
    """Spawn ``uv run <slug> serve`` in the background (detached, own session).

    Output goes to ``<target>/.serve.log`` and the process outlives the wizard on
    purpose. ``extra_path`` (e.g. a provisioned portable Node's bin dir) is prepended
    to the child's PATH so its ``npx``-based MCP servers can launch. Set the LLM key
    in the product's config page / .env to actually chat.
    """
    env = _product_env()
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


def _job_steps(needs_node: bool) -> tuple[str, ...]:
    """Ordered launch steps. ``node`` is inserted only when a Node-based MCP server
    is prefilled (it provisions a portable Node before serve). The MCP server
    package itself is fetched lazily on first connect (shown live on the product's
    MCP page), so the web opens promptly instead of waiting on a cold download."""
    if needs_node:
        return ("render", "sync", "node", "serve")
    return _LAUNCH_STEPS


def _new_job(needs_node: bool = False) -> dict:
    """A fresh launch-progress record (``render`` already done by generate())."""
    return {
        "id": uuid.uuid4().hex,
        "steps": [
            {"key": k, "status": "done" if k == "render" else "pending"}
            for k in _job_steps(needs_node)
        ],
        "url": None,
        "done": False,
        "error": None,
    }


def _set_step(job: dict, key: str, status: str) -> None:
    for step in job["steps"]:
        if step["key"] == key:
            step["status"] = status


def _run_launch(job: dict, target_dir: Path, project_slug: str, *, host: str = "127.0.0.1") -> None:
    """Worker: ``uv sync`` then start serve, updating ``job`` step-by-step."""
    try:
        # Expose the sync log so the status endpoint can stream uv's live output
        # (the install can be slow behind a firewall; without this the UI looks
        # frozen during the quiet download phase).
        job["setup_log"] = str(target_dir / ".setup.log")
        _set_step(job, "sync", "running")
        code, log_tail = _uv_sync(target_dir)
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

        _set_step(job, "serve", "running")
        job["setup_log"] = str(target_dir / ".serve.log")  # stream serve output too
        port = _find_free_port()
        _launch_product(target_dir, project_slug, port, host=host, extra_path=node_path)
        if _wait_port(host, port):
            job["url"] = f"http://{host}:{port}"
            _set_step(job, "serve", "done")
            job["done"] = True
        else:
            _set_step(job, "serve", "error")
            job["error"] = "the product web did not become reachable in time"
    except Exception as exc:  # never leave a step stuck on "running"
        for step in job["steps"]:
            if step["status"] == "running":
                step["status"] = "error"
        job["error"] = str(exc)


def _spawn_launch(job: dict, target_dir: Path, project_slug: str) -> None:
    """Start :func:`_run_launch` on a daemon thread (overridable in tests)."""
    threading.Thread(
        target=_run_launch, args=(job, target_dir, project_slug), daemon=True
    ).start()


def _with_default_tools(server):
    """Default-enable a server's tools for the wizard product (HITL-gated).

    Powerful servers (Desktop Commander) are shipped ON by default — safety is the
    ``confirm: high`` HITL gate, not off-by-default. Other servers keep the
    catalog's per-tool ``default_enabled`` state. ``replace`` keeps the frozen
    dataclass immutable."""
    if server.name not in _WIZARD_TOOLS_ON:
        return server
    return replace(
        server, tools=[replace(t, default_enabled=True) for t in server.tools]
    )


def _resolve_prefill(spec: HarnessSpec, names: list[str]):
    """Resolve catalog selections (only when mcp.enabled); raises CatalogError."""
    if spec.mcp.enabled and names:
        return [_with_default_tools(s) for s in resolve_servers([str(n) for n in names])]
    return []


def create_app() -> FastAPI:
    app = FastAPI(title="HarnessForge wizard")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    @app.get("/meta")
    def meta() -> dict:
        return {
            "paradigms": PARADIGMS,
            "catalog": _catalog_meta(),
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
            spec = HarnessSpec.model_validate(_with_defaults(dict(body.get("spec") or {})))
        except ValidationError as exc:
            return JSONResponse({"ok": False, "errors": _format_errors(exc)}, status_code=400)
        try:
            servers = _resolve_prefill(spec, body.get("mcp_servers") or [])
        except CatalogError as exc:
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "mcp_servers", "msg": str(exc)}]},
                status_code=400,
            )
        target = str(body.get("target_dir") or "").strip() or "<target-dir>"
        cmd = f"harnessforge new {target} --spec spec.yaml" + "".join(
            f" --mcp-server {s.name}" for s in servers
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
            spec = HarnessSpec.model_validate(_with_defaults(dict(body.get("spec") or {})))
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
            result = generate(
                spec,
                target_dir,
                git_init=bool(body.get("git", False)),
                mcp_servers=servers,
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
            job = _new_job(needs_node)
            _JOBS[job["id"]] = job
            _spawn_launch(job, Path(result.target_dir), result.project_slug)
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
