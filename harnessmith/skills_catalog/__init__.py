"""Bundled Agent Skills catalog — a generation-time convenience datasource.

The skills twin of :mod:`harnessmith.catalog` (MCP servers). Each subdirectory
here is a ready-made standard Agent Skill (``<name>/SKILL.md`` + optional
``scripts``/``references``/``assets``). ``harnessmith new --skill <name>`` and the
wizards copy the SELECTED skill directories verbatim into the generated repo's
``skills/<name>/`` (only when ``spec.skills.enabled``) — they are NOT part of
:class:`HarnessSpec` or its snapshot, exactly like the MCP catalog prefill.

A bundled skill is plain content (no Jinja): name + description come from the
``SKILL.md`` YAML frontmatter, the same format the generated product discovers at
runtime (``harness/skills.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CATALOG_DIR = Path(__file__).parent
SKILL_FILE = "SKILL.md"


class SkillCatalogError(Exception):
    """Raised when a requested bundled skill is missing or malformed."""


@dataclass(frozen=True)
class CatalogSkill:
    """One bundled skill: its name/description (from SKILL.md frontmatter) and the
    source directory whose files are copied into the generated repo."""

    name: str
    description: str
    source_dir: Path
    files: tuple[Path, ...] = field(default_factory=tuple)  # paths relative to source_dir


def _parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter mapping of a ``SKILL.md`` (``{}`` if none).

    Mirrors the generated product's lightweight parser: a leading ``---`` line, a
    YAML block, then a closing ``---``. Anything else is treated as bodyless."""
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def _coerce_skill(skill_dir: Path) -> CatalogSkill:
    md = skill_dir / SKILL_FILE
    meta = _parse_frontmatter(md.read_text(encoding="utf-8"))
    files = tuple(
        sorted(p.relative_to(skill_dir) for p in skill_dir.rglob("*") if p.is_file())
    )
    return CatalogSkill(
        name=str(meta.get("name") or skill_dir.name),
        description=str(meta.get("description") or "").strip(),
        source_dir=skill_dir,
        files=files,
    )


def load_skills_catalog(path: str | Path = CATALOG_DIR) -> dict[str, CatalogSkill]:
    """Load the bundled-skills catalog into a name -> :class:`CatalogSkill` map.

    A bundled skill is any direct subdirectory that contains a ``SKILL.md``. The
    catalog key is the directory name (the on-disk skill id); the SKILL.md
    ``name``/``description`` provide the display metadata."""
    base = Path(path)
    catalog: dict[str, CatalogSkill] = {}
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / SKILL_FILE).is_file():
            catalog[child.name] = _coerce_skill(child)
    return catalog


def available_skills() -> list[str]:
    """Names of bundled catalog skills."""
    return sorted(load_skills_catalog())


def resolve_skills(names: list[str]) -> list[CatalogSkill]:
    """Resolve bundled-skill names, de-duplicated, preserving first-seen order."""
    catalog = load_skills_catalog()
    resolved: list[CatalogSkill] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        if name not in catalog:
            known = ", ".join(sorted(catalog)) or "(none)"
            raise SkillCatalogError(
                f"unknown skill {name!r}; bundled skills: {known}"
            )
        resolved.append(catalog[name])
        seen.add(name)
    return resolved
