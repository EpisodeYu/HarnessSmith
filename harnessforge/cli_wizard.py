"""Interactive terminal setup wizard for ``harnessforge new`` (no --spec/--preset).

The CLI twin of the web form (``harnessforge/wizard/app.py``): it asks the same
*structural* questions (display name -> slug, language, paradigms, web/MCP/skills/
memory, catalog servers), then bakes the behavioral defaults and validates a
:class:`~harnessforge.spec.HarnessSpec` — reusing the very same baking + catalog
helpers as the web form (``harnessforge.scaffold``), so both wizards yield
identical products.

It needs ``questionary`` (a core dependency) and a real terminal; the CLI falls
back to ``--spec``/``--preset`` when there is no tty. Secrets are never
collected — only env-var NAMES (via the baked defaults).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import CatalogServer, resolve_servers
from .scaffold import (
    GENERATE_CONFIRM,
    PARADIGMS,
    WIZARD_CATALOG_DEFAULT,
    curated_catalog,
    slugify,
    with_default_tools,
    with_defaults,
)
from .spec import HarnessSpec


class WizardAborted(Exception):
    """Raised when the user cancels the interactive wizard (Ctrl-C / EOF) or when
    ``questionary`` is unavailable — the CLI reports it and exits cleanly."""


@dataclass
class WizardResult:
    """What the interactive wizard produces: a validated spec, the resolved MCP
    servers to prefill, the chosen target directory, and the HITL ``confirm``
    policy to seed (``high`` like the web wizard's products)."""

    spec: HarnessSpec
    mcp_servers: list[CatalogServer]
    target_dir: Path
    confirm_default: str


def build_spec(answers: dict) -> tuple[HarnessSpec, list[CatalogServer]]:
    """Turn structural wizard answers into a validated spec + resolved MCP servers.

    The CLI counterpart of the web wizard's ``POST /spec`` + ``/generate`` baking:
    applies :func:`with_defaults`, validates via :class:`HarnessSpec`, and (when
    MCP is on) resolves the chosen catalog servers with their wizard tool defaults.
    Raises ``pydantic.ValidationError`` / ``CatalogError`` on bad input — the same
    surfaces the CLI already handles.
    """
    display = (answers.get("display_name") or "").strip()
    spec_data: dict = {
        "project_slug": (answers.get("project_slug") or "").strip() or slugify(display),
        "language": answers.get("language") or "en",
        "paradigms": answers.get("paradigms") or ["agent"],
        "interfaces": {"cli": True, "web": bool(answers.get("web"))},
        "mcp": {"enabled": bool(answers.get("mcp"))},
        "skills": {"enabled": bool(answers.get("skills"))},
        "memory": {"enabled": bool(answers.get("memory"))},
    }
    if display:
        spec_data["display_name"] = display
    spec = HarnessSpec.model_validate(with_defaults(spec_data))

    servers: list[CatalogServer] = []
    if spec.mcp.enabled and answers.get("mcp_servers"):
        servers = [
            with_default_tools(s) for s in resolve_servers(list(answers["mcp_servers"]))
        ]
    return spec, servers


def run_wizard(*, default_target_dir: str | None = None) -> WizardResult:
    """Prompt the user (via ``questionary``) for the structural choices.

    Returns a :class:`WizardResult`. Raises :class:`WizardAborted` if the user
    cancels (Ctrl-C / EOF -> ``questionary`` returns ``None``) or if
    ``questionary`` is not installed.
    """
    try:
        import questionary
    except ImportError as exc:  # pragma: no cover - questionary is a core dep
        raise WizardAborted(
            "the interactive setup wizard needs 'questionary' (run `uv sync`). "
            "Use --spec/--preset to generate without it."
        ) from exc

    def _need(value):
        """questionary returns None on Ctrl-C / EOF — turn that into an abort."""
        if value is None:
            raise WizardAborted("setup wizard cancelled")
        return value

    answers: dict = {}
    answers["display_name"] = _need(
        questionary.text(
            "Display name (human-readable, e.g. 'My Coding Assistant'):",
            default="My Agent",
        ).ask()
    )
    suggested = slugify(answers["display_name"])
    answers["project_slug"] = _need(
        questionary.text("Package name (project_slug):", default=suggested).ask()
    )
    answers["language"] = _need(
        questionary.select(
            "Default UI language for the generated product:",
            choices=[
                questionary.Choice("English", "en"),
                questionary.Choice("中文", "zh"),
            ],
            default="en",
        ).ask()
    )
    answers["paradigms"] = _need(
        questionary.checkbox(
            "Loop paradigms to generate (first selected = runtime default):",
            choices=[
                questionary.Choice(
                    f"{p['name']} — {p['description']}", p["name"], checked=True
                )
                for p in PARADIGMS
            ],
        ).ask()
    ) or ["agent"]
    answers["web"] = _need(
        questionary.confirm("Generate a web chat + config interface?", default=True).ask()
    )
    answers["skills"] = _need(
        questionary.confirm("Enable Agent Skills (SKILL.md discovery)?", default=True).ask()
    )
    answers["memory"] = _need(
        questionary.confirm("Enable cross-session long-term memory?", default=True).ask()
    )
    answers["mcp"] = _need(
        questionary.confirm("Enable MCP tools?", default=True).ask()
    )
    if answers["mcp"]:
        answers["mcp_servers"] = _need(
            questionary.checkbox(
                "MCP servers to prefill (keys are env-var NAMES only; "
                "high-risk tools stay HITL-gated):",
                choices=[
                    questionary.Choice(
                        f"{s.name} — {s.description}" if s.description else s.name,
                        s.name,
                        checked=s.name in WIZARD_CATALOG_DEFAULT,
                    )
                    for s in curated_catalog()
                ],
            ).ask()
        )

    spec, mcp_servers = build_spec(answers)

    default_dir = default_target_dir or f"./{spec.project_slug}"
    target = _need(
        questionary.text("Generate into directory:", default=default_dir).ask()
    )

    return WizardResult(
        spec=spec,
        mcp_servers=mcp_servers,
        target_dir=Path(target.strip() or default_dir),
        confirm_default=GENERATE_CONFIRM,
    )
