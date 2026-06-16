"""Bundled-skills catalog loader tests (the skills twin of test_catalog.py)."""

from __future__ import annotations

import pytest

from harnessmith.skills_catalog import (
    SkillCatalogError,
    available_skills,
    load_skills_catalog,
    resolve_skills,
)


def test_catalog_lists_web_reading_with_metadata():
    catalog = load_skills_catalog()
    assert "web-reading" in catalog
    skill = catalog["web-reading"]
    assert skill.name == "web-reading"
    assert "r.jina.ai" in skill.description.lower() or skill.description  # has a description
    # SKILL.md is part of the copied file set.
    rels = {str(p) for p in skill.files}
    assert "SKILL.md" in rels
    assert "web-reading" in available_skills()


def test_resolve_skills_dedupes_and_validates():
    resolved = resolve_skills(["web-reading", "web-reading"])
    assert [s.name for s in resolved] == ["web-reading"]
    with pytest.raises(SkillCatalogError):
        resolve_skills(["does-not-exist"])


def test_web_reading_skill_content_is_keyless_jina():
    """The bundled skill teaches the keyless r.jina.ai fallback and carries valid
    Agent Skill frontmatter (name/description) the product can discover."""
    skill = load_skills_catalog()["web-reading"]
    body = (skill.source_dir / "SKILL.md").read_text(encoding="utf-8")
    assert body.startswith("---")  # YAML frontmatter
    assert "name: web-reading" in body
    assert "r.jina.ai" in body
