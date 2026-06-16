"""Tests for the interactive CLI setup wizard (the terminal twin of the web form).

The pure ``build_spec`` / ``slugify`` logic is exercised directly (no tty); the
``run_wizard`` prompt flow is driven with a stubbed ``questionary`` so no terminal
is needed. The wizard must reuse the same baking/catalog helpers as the web form
(``harnessmith.scaffold``) and must NOT pull FastAPI (it runs from the core CLI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnessmith.cli_wizard import WizardAborted, build_spec, run_wizard
from harnessmith.scaffold import DEFAULT_SYSTEM_PROMPT, WEB_PREFERENCE_HINT, slugify


@pytest.mark.parametrize(
    "display,expected",
    [
        ("My Coding Assistant", "my_coding_assistant"),
        ("  Spaced  Name  ", "spaced_name"),
        ("Hello-World!", "hello_world"),
        ("123 bot", "_123_bot"),  # leading digit gets an underscore prefix
        ("!!!", "agent_harness"),  # nothing usable -> the form's fallback
        ("", "agent_harness"),
    ],
)
def test_slugify_mirrors_web_derive_slug(display, expected):
    assert slugify(display) == expected


def test_build_spec_bakes_behavioral_defaults_from_structural_answers():
    """Structural-only answers -> a validated spec with the same baked LLM /
    prompt defaults the web form produces (runnable out of the box)."""
    spec, servers = build_spec(
        {
            "display_name": "My Coding Assistant",
            "language": "zh",
            "paradigms": ["agent", "plan"],
            "web": True,
            "mcp": False,
            "skills": True,
            "memory": True,
        }
    )
    assert spec.project_slug == "my_coding_assistant"
    assert spec.display_name == "My Coding Assistant"
    assert spec.language == "zh"
    assert spec.paradigms == ["agent", "plan"]
    assert spec.interfaces.web is True and spec.interfaces.cli is True
    assert spec.skills.enabled is True and spec.memory.enabled is True
    # baked behavioral defaults (env-var NAMES only, no guessed model)
    assert spec.llms and spec.llms[0].name == "default" and spec.llms[0].model == ""
    assert spec.llms[0].api_key_env == "OPENAI_API_KEY"
    assert spec.prompts.system == DEFAULT_SYSTEM_PROMPT
    assert servers == []


def test_build_spec_resolves_mcp_servers_with_wizard_tool_defaults():
    """When MCP is on, chosen catalog servers are resolved and Desktop Commander's
    tools are default-enabled (HITL-gated), matching the web wizard product."""
    spec, servers = build_spec(
        {
            "display_name": "Tooly",
            "mcp": True,
            "mcp_servers": ["fetch", "desktop-commander"],
        }
    )
    assert spec.mcp.enabled is True
    names = [s.name for s in servers]
    assert names == ["fetch", "desktop-commander"]
    dc = next(s for s in servers if s.name == "desktop-commander")
    assert dc.tools and all(t.default_enabled for t in dc.tools)


def test_build_spec_ignores_servers_when_mcp_disabled():
    _, servers = build_spec({"display_name": "x", "mcp": False, "mcp_servers": ["fetch"]})
    assert servers == []


def test_build_spec_appends_web_pref_when_upgrade_server_selected():
    """Prefilling a key-based upgrade (Bocha / Jina) appends the soft preference
    hint to the seeded system prompt — advisory, after the base prompt."""
    spec, _ = build_spec(
        {"display_name": "x", "mcp": True, "mcp_servers": ["web-search", "bocha"]}
    )
    assert spec.prompts.system != DEFAULT_SYSTEM_PROMPT
    assert spec.prompts.system.startswith(DEFAULT_SYSTEM_PROMPT)
    assert spec.prompts.system.endswith(WEB_PREFERENCE_HINT)


def test_build_spec_no_web_pref_without_upgrade_server():
    """No upgrade server -> system prompt stays byte-identical to the default
    (the runtime fallback invariant holds for non-upgrade products)."""
    spec, _ = build_spec(
        {"display_name": "x", "mcp": True, "mcp_servers": ["fetch", "git"]}
    )
    assert spec.prompts.system == DEFAULT_SYSTEM_PROMPT


def test_build_spec_rejects_invalid_slug():
    with pytest.raises(ValidationError):
        build_spec({"project_slug": "1bad", "paradigms": ["agent"]})


def test_build_spec_defaults_paradigms_to_agent_when_empty():
    spec, _ = build_spec({"display_name": "x", "paradigms": []})
    assert spec.paradigms == ["agent"]


class _Answer:
    """A stub for ``questionary``'s prompt objects: ``.ask()`` returns the value."""

    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value


def _stub_questionary(monkeypatch, *, texts, select, checkboxes, confirms):
    import questionary

    text_q, cb_q, cf_q = list(texts), list(checkboxes), list(confirms)
    monkeypatch.setattr(questionary, "text", lambda *a, **k: _Answer(text_q.pop(0)))
    monkeypatch.setattr(questionary, "select", lambda *a, **k: _Answer(select))
    monkeypatch.setattr(questionary, "checkbox", lambda *a, **k: _Answer(cb_q.pop(0)))
    monkeypatch.setattr(questionary, "confirm", lambda *a, **k: _Answer(cf_q.pop(0)))


def test_run_wizard_builds_result_from_answers(monkeypatch):
    _stub_questionary(
        monkeypatch,
        texts=["My Coding Assistant", "", "./out"],  # display, slug (blank->derive), dir
        select="zh",
        checkboxes=[["agent", "plan"], ["fetch", "git"]],  # paradigms, mcp servers
        confirms=[True, True, True, True],  # web, skills, memory, mcp
    )
    result = run_wizard()
    assert result.spec.project_slug == "my_coding_assistant"
    assert result.spec.language == "zh"
    assert result.spec.interfaces.web is True
    assert result.spec.mcp.enabled is True
    assert [s.name for s in result.mcp_servers] == ["fetch", "git"]
    assert result.target_dir == Path("./out")
    # Wizard products seed the high HITL confirm policy, like the web form.
    assert result.confirm_default == "high"


def test_run_wizard_skips_server_prompt_when_mcp_off(monkeypatch):
    _stub_questionary(
        monkeypatch,
        texts=["Plain", "plain", "./plain"],
        select="en",
        checkboxes=[["agent"]],  # only the paradigms checkbox is consumed
        confirms=[False, False, False, False],  # web, skills, memory, mcp all off
    )
    result = run_wizard()
    assert result.spec.mcp.enabled is False
    assert result.mcp_servers == []


def test_run_wizard_aborts_when_user_cancels(monkeypatch):
    """questionary returns None on Ctrl-C / EOF -> the wizard raises WizardAborted."""
    import questionary

    monkeypatch.setattr(questionary, "text", lambda *a, **k: _Answer(None))
    with pytest.raises(WizardAborted):
        run_wizard()


def test_cli_wizard_imports_without_fastapi():
    """Red line: the CLI wizard path (scaffold + cli_wizard) must stay FastAPI-free
    so `uvx harnessmith new` never pulls the wizard extra."""
    code = (
        "import harnessmith.cli_wizard, harnessmith.scaffold, sys; "
        "assert 'fastapi' not in sys.modules, sorted(sys.modules)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
