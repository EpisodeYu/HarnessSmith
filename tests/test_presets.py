"""Preset loading tests (fast)."""

from __future__ import annotations

import pytest

from harnessforge.presets import (
    PresetNotFoundError,
    available_presets,
    preset_spec_path,
)
from harnessforge.spec import load_spec


def test_coding_assistant_preset_is_available():
    assert "coding-assistant" in available_presets()


def test_coding_assistant_preset_is_a_valid_spec():
    spec = load_spec(preset_spec_path("coding-assistant"))
    assert spec.project_slug == "coding_assistant"
    assert spec.roles == {"generation": "default"}
    assert {tool.name for tool in spec.tools} == {"get_current_time", "calculator"}
    assert spec.budget.max_steps == 8


def test_unknown_preset_raises():
    with pytest.raises(PresetNotFoundError):
        preset_spec_path("does-not-exist")
