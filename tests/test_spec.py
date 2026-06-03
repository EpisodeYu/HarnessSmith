"""Spec validation tests (Slice 0)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from harnessforge.spec import HarnessSpec, load_spec

EXAMPLE_SPEC = Path(__file__).resolve().parents[1] / "examples" / "spec.yaml"


def test_example_spec_is_valid():
    spec = load_spec(EXAMPLE_SPEC)
    assert spec.project_slug == "agent_harness"
    assert spec.version == "0.1"
    assert [p.name for p in spec.llms] == ["default"]
    assert spec.roles == {"generation": "default"}
    assert spec.interfaces.cli is True
    assert spec.prompts.system == "You are a helpful assistant."
    assert spec.budget.max_steps == 8


def test_defaults_fill_in_minimal_spec():
    spec = HarnessSpec()
    assert spec.project_slug == "agent_harness"
    assert spec.interfaces.cli is True
    assert spec.observability.trace_dir == "traces"
    assert spec.prompts.system is None and spec.prompts.persona is None
    assert spec.budget.max_steps is None
    assert spec.context is None and spec.rag is None and spec.secrets is None


@pytest.mark.parametrize("field", ["max_steps", "max_seconds", "max_cost_usd"])
def test_non_positive_budget_is_rejected(field):
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"budget": {field: 0}})


def test_unknown_top_level_field_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"project_slug": "x", "not_a_field": 1})


def test_unknown_nested_field_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate(
            {"llms": [{"name": "a", "model": "m", "bogus": True}]}
        )


@pytest.mark.parametrize("bad_slug", ["1agent", "Agent", "my-agent", "with space", ""])
def test_invalid_project_slug_is_rejected(bad_slug):
    with pytest.raises(ValidationError):
        HarnessSpec(project_slug=bad_slug)


def test_role_referencing_unknown_profile_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate(
            {
                "llms": [{"name": "default", "model": "m"}],
                "roles": {"generation": "missing"},
            }
        )


def test_reserved_fields_pass_through():
    spec = HarnessSpec.model_validate({"context": {"strategy": "truncate"}})
    assert spec.context == {"strategy": "truncate"}


def test_load_spec_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_spec(tmp_path / "nope.yaml")


def test_load_spec_non_mapping_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_spec(bad)


def test_api_key_is_a_name_not_a_value():
    """Guardrail: profiles store env-var NAMES, not secret values."""
    spec = load_spec(EXAMPLE_SPEC)
    dumped = yaml.safe_dump(spec.model_dump(mode="json"))
    assert "OPENAI_API_KEY" in dumped  # the name is present...
    assert "sk-" not in dumped  # ...but no secret-looking value
