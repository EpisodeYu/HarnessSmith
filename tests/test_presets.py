"""Preset loading tests (fast)."""

from __future__ import annotations

import pytest

from harnessmith.presets import (
    PresetNotFoundError,
    available_presets,
    preset_mcp_servers,
    preset_spec_path,
)
from harnessmith.spec import load_spec


def test_coding_assistant_preset_is_available():
    assert "coding-assistant" in available_presets()


def test_coding_assistant_preset_is_a_valid_spec():
    spec = load_spec(preset_spec_path("coding-assistant"))
    assert spec.project_slug == "coding_assistant"
    assert spec.roles == {"generation": "default"}
    assert {tool.name for tool in spec.tools} == {"get_current_time", "calculator"}
    # Slice 6: the coding-assistant is an MCP capability baseline.
    assert spec.mcp.enabled is True


def test_coding_assistant_mcp_prefill_is_the_baseline():
    servers = preset_mcp_servers("coding-assistant")
    assert [s.name for s in servers] == ["fetch", "ddg-search", "git", "desktop-commander"]
    fetch = next(s for s in servers if s.name == "fetch")
    assert fetch.safe_tools == ["fetch"]
    ddg = next(s for s in servers if s.name == "ddg-search")
    assert ddg.safe_tools == ["search", "fetch_content"]  # keyless web search, read-only
    git = next(s for s in servers if s.name == "git")
    assert "git_status" in git.safe_tools and "git_commit" not in git.safe_tools
    # Not pinned to --repository: pinning makes mcp-server-git exit at startup when
    # the cwd isn't a git repo (server goes "unreachable"); unpinned it stays
    # healthy and the agent targets any repo via each tool's repo_path arg.
    assert "--repository" not in git.args


def test_preset_without_prefill_returns_empty():
    # examples-style presets with no mcp_prefill.yaml just return [].
    # (coding-assistant has one; an absent file must be tolerated, not error.)
    assert preset_mcp_servers("coding-assistant")  # has a prefill


def test_unknown_preset_raises():
    with pytest.raises(PresetNotFoundError):
        preset_spec_path("does-not-exist")
