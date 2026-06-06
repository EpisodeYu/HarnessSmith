"""FastAPI app for the spec wizard (Slice 7).

Routes:

- ``GET /``          — the single-page form (no build; Tailwind CDN + vanilla JS).
- ``GET /meta``      — field metadata the form needs (paradigms, built-in tools,
  MCP catalog, presets).
- ``POST /spec``     — validate the form via :class:`HarnessSpec`; return spec
  YAML + the matching ``harnessforge new`` command, or field-level errors.
- ``POST /generate`` — optionally render the spec into an owned repo (the same
  ``generate()`` the CLI uses; render-only so the UI stays snappy/offline — the
  user runs ``uv sync`` after, or relays via ``harnessforge new --spec``).

Secrets are never collected or returned — only env-var NAMES. This module imports
FastAPI, so it is only imported on demand (the ``harnessforge wizard`` command),
keeping the core CLI / ``uvx harnessforge new`` free of the wizard dependencies.
"""

from __future__ import annotations

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

# The built-in demo tools the templates ship (tools.py). Real capabilities come
# from MCP servers (the catalog); these two are safe, read-only examples.
BUILTIN_TOOLS = [
    {"name": "get_current_time", "description": "Return the current UTC time (ISO 8601)."},
    {"name": "calculator", "description": "Evaluate a basic arithmetic expression."},
]

# The built-in loop paradigms (cf. spec.paradigms' Literal). agent is the default
# tool-calling loop; plan/ask are read-only.
PARADIGMS = [
    {"name": "agent", "description": "Default tool-calling loop (ReAct-style; self-corrects on tool errors)."},
    {"name": "plan", "description": "Read-only: investigates with low-risk tools and outputs a step-by-step plan."},
    {"name": "ask", "description": "Read-only: answers questions with low-risk tools; never mutates."},
]


# Optional, opt-in default-language directive appended to prompts.system. It is
# *soft* (still match the user's actual input language) because modern models
# already auto-detect input language — this only pins the default for ambiguous
# input. Becomes editable text in config.yaml's prompts.system, so it's a normal
# runtime knob afterwards.
_LANG_DIRECTIVE = {
    "en": "Respond in English by default; if the user writes in another language, reply in theirs.",
    "zh": "默认用中文回答;如果用户使用其他语言,则用用户的语言回答。",
}


def _apply_language_directive(spec_data: dict) -> dict:
    """Append the default-language directive to prompts.system (opt-in)."""
    directive = _LANG_DIRECTIVE.get(str(spec_data.get("language", "en")))
    if not directive:
        return spec_data
    prompts = dict(spec_data.get("prompts") or {})
    system = (prompts.get("system") or "").strip()
    prompts["system"] = f"{system}\n\n{directive}" if system else directive
    return {**spec_data, "prompts": prompts}


def _spec_from_body(body: dict) -> dict:
    """Pull the spec dict out of a request body, applying opt-in language directive."""
    spec_data = dict(body.get("spec") or {})
    if body.get("llm_language"):
        spec_data = _apply_language_directive(spec_data)
    return spec_data


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
    servers = []
    for _, s in sorted(load_catalog().items()):
        servers.append(
            {
                "name": s.name,
                "description": s.description,
                "transport": s.transport,
                "requires": s.requires,
                "tools": [
                    {"name": t.name, "risk": t.risk, "default_enabled": t.default_enabled}
                    for t in s.tools
                ],
            }
        )
    return servers


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
            "builtin_tools": BUILTIN_TOOLS,
            "catalog": _catalog_meta(),
            "presets": available_presets(),
        }

    @app.post("/spec")
    async def post_spec(request: Request):
        body = await request.json()
        try:
            spec = HarnessSpec.model_validate(_spec_from_body(body))
        except ValidationError as exc:
            return JSONResponse({"ok": False, "errors": _format_errors(exc)}, status_code=400)
        try:
            servers = _resolve_prefill(spec, body.get("mcp_servers") or [])
        except CatalogError as exc:
            return JSONResponse(
                {"ok": False, "errors": [{"loc": "mcp_servers", "msg": str(exc)}]},
                status_code=400,
            )
        cmd = "harnessforge new <target-dir> --spec spec.yaml" + "".join(
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
            spec = HarnessSpec.model_validate(_spec_from_body(body))
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
        return {
            "ok": True,
            "target_dir": str(result.target_dir),
            "project_slug": result.project_slug,
            "files": len(result.written_files),
            "next": (
                f"cd {result.target_dir} && uv sync && "
                f'uv run {result.project_slug} run --mock "hello"'
            ),
        }

    return app


app = create_app()
