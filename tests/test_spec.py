"""Spec validation tests (Slice 0)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from harnessmith.scaffold import DEFAULT_SYSTEM_PROMPT
from harnessmith.spec import HarnessSpec, load_spec

EXAMPLE_SPEC = Path(__file__).resolve().parents[1] / "examples" / "spec.yaml"


def test_example_spec_is_valid():
    spec = load_spec(EXAMPLE_SPEC)
    assert spec.project_slug == "agent_harness"
    assert spec.version == "0.1"
    assert [p.name for p in spec.llms] == ["default"]
    assert spec.roles == {"generation": "default"}
    assert spec.interfaces.cli is True
    assert spec.prompts.system == DEFAULT_SYSTEM_PROMPT


def test_defaults_fill_in_minimal_spec():
    spec = HarnessSpec()
    assert spec.project_slug == "agent_harness"
    assert spec.interfaces.cli is True
    assert spec.observability.trace_dir == "traces"
    assert spec.prompts.system is None
    assert spec.mcp.enabled is False  # MCP capability is opt-in (Slice 4)
    assert spec.subagents.enabled is False  # multi-agent subagents are opt-in
    assert spec.paradigms == ["agent"]  # only the agent loop by default (Slice 5)
    assert spec.context is None and spec.rag is None and spec.secrets is None


def test_mcp_enabled_is_accepted():
    spec = HarnessSpec.model_validate({"mcp": {"enabled": True}})
    assert spec.mcp.enabled is True


def test_subagents_enabled_is_accepted():
    spec = HarnessSpec.model_validate({"subagents": {"enabled": True}})
    assert spec.subagents.enabled is True


def test_subagents_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"subagents": {"enabled": True, "agents": []}})


def test_display_name_defaults_to_none():
    assert HarnessSpec().display_name is None


def test_display_name_is_accepted():
    spec = HarnessSpec.model_validate({"display_name": "My Coding Assistant"})
    assert spec.display_name == "My Coding Assistant"


def test_display_name_allows_context_sensitive_punctuation():
    name = 'Eve "Bot" \\ <>&'
    assert HarnessSpec(display_name=name).display_name == name


@pytest.mark.parametrize(
    "display_name",
    [
        "line one\nline two",
        "tab\tname",
        "control\x7fname",
        "control\u0085name",
        "line\u2028separator",
        "x" * 121,
        "   ",
    ],
)
def test_display_name_rejects_multiline_controls_long_and_blank(display_name):
    with pytest.raises(ValidationError):
        HarnessSpec(display_name=display_name)


def test_language_defaults_to_en():
    assert HarnessSpec().language == "en"


def test_trace_dir_cannot_inject_gitignore_lines():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"observability": {"trace_dir": "traces\n!.env"}})


def test_language_accepts_zh():
    assert HarnessSpec.model_validate({"language": "zh"}).language == "zh"


def test_invalid_language_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"language": "fr"})


def test_paradigms_default_is_agent():
    spec = HarnessSpec()
    assert spec.paradigms == ["agent"]


def test_paradigms_multiselect_is_accepted():
    spec = HarnessSpec.model_validate({"paradigms": ["agent", "plan", "ask"]})
    assert spec.paradigms == ["agent", "plan", "ask"]


def test_paradigms_are_deduped_preserving_order():
    spec = HarnessSpec.model_validate({"paradigms": ["plan", "agent", "plan", "ask"]})
    assert spec.paradigms == ["plan", "agent", "ask"]


def test_empty_paradigms_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"paradigms": []})


def test_unknown_paradigm_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"paradigms": ["agent", "reflection"]})


def test_mcp_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"mcp": {"enabled": True, "servers": []}})


def test_budget_block_is_rejected():
    """Per-LLM cost limits are runtime-only (config.yaml); the spec has no budget
    block, so an old budget: block is now rejected under extra='forbid'."""
    with pytest.raises(ValidationError):
        HarnessSpec.model_validate({"budget": {"conditions": {"max_steps": 8}}})


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("api_key_env", "sk-proj-secret-value"),
        ("api_key_env", "ghp_abcdefghijklmnopqrstuvwxyz123456"),
        ("api_key_env", "AKIAIOSFODNN7EXAMPLE"),
        ("base_url_env", "https://user:secret@example.test/v1"),
        ("base_url_env", "bad name"),
    ],
)
def test_env_references_reject_values_without_echoing_them(field, value):
    with pytest.raises(ValidationError) as caught:
        HarnessSpec.model_validate(
            {"llms": [{"name": "default", "model": "m", field: value}]}
        )
    rendered = str(caught.value)
    assert value not in rendered
    assert "environment-variable name" in rendered


@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "_PRIVATE_TOKEN", "lowercase_2"])
def test_env_references_accept_valid_names(name):
    spec = HarnessSpec.model_validate(
        {"llms": [{"name": "default", "model": "m", "api_key_env": name}]}
    )
    assert spec.llms[0].api_key_env == name


def test_llm_provider_defaults_to_openai():
    spec = HarnessSpec(llms=[{"name": "d", "model": "gpt-4o-mini"}])
    assert spec.llms[0].provider == "openai"


def test_llm_provider_anthropic_is_accepted():
    spec = HarnessSpec(
        llms=[
            {
                "name": "claude",
                "model": "claude-opus-4-8",
                "provider": "anthropic",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        ]
    )
    assert spec.llms[0].provider == "anthropic"


def test_llm_provider_unknown_is_rejected():
    with pytest.raises(ValidationError):
        HarnessSpec(llms=[{"name": "d", "model": "m", "provider": "gemini"}])
