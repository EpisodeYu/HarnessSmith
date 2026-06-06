"""FastAPI app for the spec wizard (Slice 7).

Routes:

- ``GET /``          — the single-page form (no build; Tailwind CDN + vanilla JS).
- ``GET /meta``      — field metadata the form needs (paradigms, built-in tools,
  MCP catalog, presets).
- ``POST /spec``     — validate the form via :class:`HarnessSpec`; return spec
  YAML + the matching ``harnessforge new`` command, or field-level errors.
- ``POST /generate`` — render the spec into an owned repo (the same ``generate()``
  the CLI uses). With ``launch: true`` (and a Web-enabled spec) it also stands the
  product's web server up in the background (``uv run <slug> serve``) and returns a
  URL to open; otherwise it stays render-only (the user runs ``uv sync`` after, or
  relays via ``harnessforge new --spec``).

Secrets are never collected or returned — only env-var NAMES. This module imports
FastAPI, so it is only imported on demand (the ``harnessforge wizard`` command),
keeping the core CLI / ``uvx harnessforge new`` free of the wizard dependencies.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from ..catalog import CatalogError, load_catalog, resolve_servers
from ..generator import TargetExistsError, generate
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
# enabled tools) and ``time`` (niche) are hidden here. Desktop Commander is shown
# but unchecked (all tools high-risk) and ordered last.
_WIZARD_CATALOG_ORDER = ("fetch", "ddg-search", "git", "desktop-commander")
_WIZARD_CATALOG_DEFAULT = frozenset({"fetch", "ddg-search", "git"})

# Background product servers launched by the one-click "generate" flow. Held so
# the Popen handles (and their log file objects) aren't garbage-collected; the
# processes are detached (own session) and outlive the wizard on purpose.
_LAUNCHED: list[subprocess.Popen] = []

# Behavioral defaults baked into the spec when the (structural-only) wizard form
# omits them. The wizard intentionally hides these — a generator can produce many
# products, each configuring its own LLM / prompts / budget at runtime in the
# product's own config page / .env. Baking sensible defaults keeps the generated
# product complete and runnable out of the box. Secrets are env-var NAMES only.
# Only filled when absent/empty, so an explicit spec (or a hand-written one) wins.
_BAKED_DEFAULTS: dict = {
    "llms": [
        {
            "name": "default",
            "model": "gpt-4o-mini",
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
    "budget": {"max_steps": 8},
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


def _launch_product(target_dir: Path, project_slug: str, *, host: str = "127.0.0.1") -> str:
    """Spawn the generated product's web server in the background; return its URL.

    Runs ``uv run <slug> serve`` (real mode — uv syncs deps on first launch, which
    can take a moment). Detached into its own session with output redirected to
    ``<target>/.serve.log`` so the product keeps serving after the wizard stops.
    Set the LLM key in the product's config page / .env to actually chat.
    """
    port = _find_free_port()
    log = (target_dir / ".serve.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(  # noqa: S603 — local dev convenience, fixed argv
        ["uv", "run", project_slug, "serve", "--host", host, "--port", str(port)],
        cwd=str(target_dir),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _LAUNCHED.append(proc)
    return f"http://{host}:{port}"


def _resolve_prefill(spec: HarnessSpec, names: list[str]):
    """Resolve catalog selections (only when mcp.enabled); raises CatalogError."""
    if spec.mcp.enabled and names:
        return resolve_servers([str(n) for n in names])
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
                spec, target_dir, git_init=bool(body.get("git", False)), mcp_servers=servers
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
        # One-click launch: stand the product's web up and hand back a URL. Only
        # meaningful when the Web interface was generated; render-only otherwise.
        if body.get("launch") and spec.interfaces.web:
            try:
                resp["url"] = _launch_product(
                    Path(result.target_dir), result.project_slug
                )
            except OSError as exc:
                resp["launch_error"] = str(exc)
        return resp

    return app


app = create_app()
