"""Shared, FastAPI-free scaffolding helpers for the structural-only wizards.

Both wizards collect only *what to generate* (display name -> slug, language,
paradigms, web/MCP/skills/memory, catalog servers):

- the web form (``harnessmith/wizard/app.py``, ``[wizard]`` extra), and
- the interactive CLI wizard (``harnessmith new`` with no ``--spec``/``--preset``).

Behavioral fields (llms/prompts/tools) are baked here with working defaults so
the generated product is runnable out of the box and tuned later in the product's
own config page (LLM pricing + cost limits live on its Budget page). Secrets are
env-var NAMES only, never values.

This module deliberately does NOT import FastAPI/uvicorn: it is reachable from
the core CLI (``uvx harnessmith new``), which must stay free of the ``wizard``
extra.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .catalog import CatalogServer, load_catalog

# The built-in loop paradigms (cf. spec.paradigms' Literal). agent is the default
# tool-calling loop; plan/ask are read-only.
PARADIGMS = [
    {"name": "agent", "description": "Default tool-calling loop (ReAct-style; self-corrects on tool errors)."},
    {"name": "plan", "description": "Read-only: investigates with low-risk tools and outputs a step-by-step plan."},
    {"name": "ask", "description": "Read-only: answers questions with low-risk tools; never mutates."},
]

# Which catalog servers the wizards surface, in display order, and which are
# checked by default. The catalog itself keeps every server (``--mcp-server``
# still resolves e.g. github/time) — this only curates the *forms*. ``git`` is the
# practical local default (keyless, read tools on); ``github`` (needs a token, no
# enabled tools) and ``time`` (niche) are hidden here. Desktop Commander (shell +
# full filesystem) is default-ON in the wizard product — safety is the HITL
# confirmation gate (``confirm: high``, see ``GENERATE_CONFIRM``), a deliberate,
# signed loosening of the "high-risk off by default" baseline for wizard products
# only (Slice 11). It still needs Node (npx) at runtime.
WIZARD_CATALOG_ORDER = ("fetch", "ddg-search", "git", "desktop-commander")
WIZARD_CATALOG_DEFAULT = frozenset({"fetch", "ddg-search", "git", "desktop-commander"})

# Catalog servers whose tools the wizards ship ENABLED by default (overriding the
# catalog's off-by-default state). Powerful but HITL-gated (``confirm: high``).
WIZARD_TOOLS_ON = frozenset({"desktop-commander"})

# HITL confirmation policy seeded into a wizard product's config.yaml: every
# risk=high tool (shell / file writes / Desktop Commander) pauses for the user's
# OK before it runs. The plain CLI (--spec/--preset) path keeps the "none" default.
GENERATE_CONFIRM = "high"

# The default base system prompt seeded into wizard/CLI-scaffolded products. Kept
# byte-identical to the runtime fallback (generated harness/prompts.py) and the
# example spec. Thin and general on purpose (this is a generic harness, not a
# coding-only one): project/domain specifics belong in rule files, not here.
DEFAULT_SYSTEM_PROMPT = (
    "You are a capable AI assistant. You operate in an agent loop: you can call "
    "the tools available to you, observe the results, and keep going until the "
    "user's request is resolved.\n\n"
    "- Use the available tools when they help; don't guess at anything you can "
    "look up or verify with a tool.\n"
    "- Be honest and accurate. If you're unsure or can't determine something, say "
    "so; never fabricate facts, code, file contents, command output, or URLs.\n"
    "- See the task through, then stop and briefly report what you did and any "
    "next steps.\n"
    "- Be concise and direct: lead with the result, skip filler and unnecessary "
    "preamble, and don't use emojis unless asked.\n"
    "- Do what was asked: prefer the simplest correct approach and avoid "
    "unrequested scope or complexity.\n\n"
    "When project-specific rules are provided to you, follow them; they take "
    "precedence over these defaults."
)

# Behavioral defaults baked into the spec when the (structural-only) wizard forms
# omit them. A generator can produce many products, each configuring its own LLM /
# prompts / budget at runtime in the product's own config page / .env; baking
# sensible defaults keeps the generated product complete and runnable out of the
# box. Secrets are env-var NAMES only. Only filled when absent/empty, so an
# explicit spec (or a hand-written one) wins.
BAKED_DEFAULTS: dict = {
    # The LLM profile is scaffolded with the env-var NAMES but NO model: the
    # wizard never asks which model, so guessing one (gpt-4o-mini) only mis-fires
    # on non-OpenAI providers. The generated product gates chat until the user
    # sets a model on its own config page (+ the key in .env).
    "llms": [
        {
            "name": "default",
            "model": "",
            "api_key_env": "OPENAI_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
        }
    ],
    "roles": {"generation": "default"},
    "prompts": {"system": DEFAULT_SYSTEM_PROMPT},
    "tools": [
        {"name": "get_current_time", "enabled": True},
        {"name": "calculator", "enabled": True},
    ],
}

_SLUG_SUB = re.compile(r"[^a-z0-9]+")


def with_defaults(spec_data: dict) -> dict:
    """Fill behavioral defaults the structural-only wizards omit."""
    out = dict(spec_data)
    for key, value in BAKED_DEFAULTS.items():
        if not out.get(key):
            out[key] = value
    return out


def with_default_tools(server: CatalogServer) -> CatalogServer:
    """Default-enable a server's tools for the wizard product (HITL-gated).

    Powerful servers (Desktop Commander) are shipped ON by default — safety is the
    ``confirm: high`` HITL gate, not off-by-default. Other servers keep the
    catalog's per-tool ``default_enabled`` state. ``replace`` keeps the frozen
    dataclass immutable."""
    if server.name not in WIZARD_TOOLS_ON:
        return server
    return replace(
        server, tools=[replace(t, default_enabled=True) for t in server.tools]
    )


def curated_catalog() -> list[CatalogServer]:
    """The catalog servers the wizards surface, in curated display order."""
    catalog = load_catalog()
    return [catalog[name] for name in WIZARD_CATALOG_ORDER if name in catalog]


def slugify(display_name: str | None) -> str:
    """Derive a snake_case ``project_slug`` from a display name.

    Mirrors the web wizard's JS (``deriveSlug``): lowercase, collapse non-alnum
    runs to ``_``, trim leading/trailing ``_``, and prefix a leading digit. Falls
    back to ``agent_harness`` when nothing usable remains (the form's default)."""
    slug = _SLUG_SUB.sub("_", (display_name or "").lower().strip()).strip("_")
    if slug and slug[0].isdigit():
        slug = "_" + slug
    return slug or "agent_harness"
