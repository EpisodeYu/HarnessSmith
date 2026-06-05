"""HarnessSpec — the minimal spec model that drives generation (Slice 0).

Field names here become the field names of the generated ``config.yaml`` later,
so they are deliberately conservative. Secrets are NEVER stored as values: LLM
profiles reference environment-variable *names* (``api_key_env`` / ``base_url_env``),
and real values live only in ``.env``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class LLMProfile(BaseModel):
    """A named LLM configuration (placeholder in Slice 0; expanded in Slice 1)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    base_url_env: str | None = None


class ToolSpec(BaseModel):
    """A tool entry (placeholder in Slice 0; real registration arrives in Slice 1)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool = True


class Interfaces(BaseModel):
    """Which interfaces the generated repo should expose."""

    model_config = ConfigDict(extra="forbid")

    cli: bool = True
    web: bool = False  # L2 (Slice 3)


class Mcp(BaseModel):
    """Opt-in MCP tool capability (L2, Slice 4).

    Generation-time decides ONLY whether the capability exists: ``enabled``
    renders ``harness/mcp.py`` and adds the ``mcp`` dependency. *Which* servers
    to connect to, which tools to allowlist, and which transport (stdio vs
    remote HTTP/SSE) are runtime knobs in ``config.yaml`` — they are NOT part of
    the spec. Disabled leaves the generated repo with zero MCP footprint.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class Skills(BaseModel):
    """Opt-in standard Agent Skills support (L2/L3, Slice 6).

    Like :class:`Mcp`, generation-time decides ONLY whether the capability
    exists: ``enabled`` renders ``harness/skills.py`` (SKILL.md discovery + L1
    system-prompt injection + a ``read_skill`` tool) and a ``skills`` block in
    ``config.yaml``. *Where* to discover skills is a runtime knob
    (``config.yaml`` ``skills.dirs``), not a spec field. Disabled leaves the
    generated repo with zero skills footprint.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class Observability(BaseModel):
    """Tracing / cost-accounting settings."""

    model_config = ConfigDict(extra="forbid")

    trace: bool = True
    trace_dir: str = "traces"


class Prompts(BaseModel):
    """System-prompt assembly inputs (consumed by prompts.py in Slice 1)."""

    model_config = ConfigDict(extra="forbid")

    system: str | None = None
    persona: str | None = None
    # Always-apply project rule files (the open AGENTS.md / CLAUDE.md / .cursor
    # rules pattern): paths to markdown files whose text is injected into every
    # system prompt. This is only a *seed* for the runtime knob — it is rendered
    # into ``config.yaml`` (``prompts.rules_files``) where it stays editable
    # without regenerating. Empty means no rule files (zero footprint). A listed
    # ``RULES.md`` also gets a starter file generated into the repo.
    rules_files: list[str] = Field(default_factory=list)


class Budget(BaseModel):
    """Per-run guardrail budget; ``None`` means no limit.

    Declared in Slice 0; enforcement (budget-stop) is wired in Slice 1.
    """

    model_config = ConfigDict(extra="forbid")

    max_steps: int | None = Field(default=None, gt=0)
    max_seconds: float | None = Field(default=None, gt=0)
    max_cost_usd: float | None = Field(default=None, gt=0)


class HarnessSpec(BaseModel):
    """Minimal HarnessSpec for Slice 0.

    ``context`` / ``rag`` / ``secrets`` are declared for forward compatibility but
    are not interpreted in Slice 0 — they are passed through untouched.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = "0.1"
    project_slug: str = "agent_harness"
    llms: list[LLMProfile] = Field(default_factory=list)
    roles: dict[str, str] = Field(default_factory=dict)
    prompts: Prompts = Field(default_factory=Prompts)
    tools: list[ToolSpec] = Field(default_factory=list)
    # Which built-in loop paradigms to render into the repo (Slice 5). The set
    # mirrors the modern product trio (cf. Cursor Agent/Ask/Plan): ``agent`` is
    # the default tool-calling loop (ReAct-style, self-corrects on tool/error
    # observations); ``plan``/``ask`` are read-only. The registry under
    # harness/paradigms/ is ALWAYS generated; this list decides which built-in
    # paradigm *files* exist (structural = generation-time). The first entry
    # seeds the runtime default in config.yaml. Which are selectable at runtime,
    # and any paradigm you add yourself, live in config.yaml's
    # `paradigms.enabled` (behavioral = runtime).
    paradigms: list[Literal["agent", "plan", "ask"]] = Field(
        default_factory=lambda: ["agent"]
    )
    interfaces: Interfaces = Field(default_factory=Interfaces)
    mcp: Mcp = Field(default_factory=Mcp)
    skills: Skills = Field(default_factory=Skills)
    observability: Observability = Field(default_factory=Observability)
    budget: Budget = Field(default_factory=Budget)

    # Reserved for later slices: declared so specs stay forward-compatible under
    # extra="forbid", but not used by the Slice 0 generator.
    context: dict[str, Any] | None = None
    rag: dict[str, Any] | None = None
    secrets: dict[str, Any] | None = None

    @field_validator("paradigms")
    @classmethod
    def _validate_paradigms(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("paradigms must list at least one paradigm")
        deduped: list[str] = []
        for name in value:
            if name not in deduped:
                deduped.append(name)
        return deduped

    @field_validator("project_slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        if not _SLUG_RE.match(value):
            raise ValueError(
                "project_slug must be a snake_case Python identifier "
                "(lowercase letters, digits, underscores; not starting with a digit), "
                f"got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _validate_role_targets(self) -> "HarnessSpec":
        if self.roles and self.llms:
            known = {profile.name for profile in self.llms}
            unknown = {target for target in self.roles.values() if target not in known}
            if unknown:
                raise ValueError(
                    f"roles reference unknown LLM profile(s) {sorted(unknown)}; "
                    f"known profiles are {sorted(known)}"
                )
        return self


def load_spec(path: str | Path) -> HarnessSpec:
    """Load and validate a HarnessSpec from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"spec file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(
            "spec file must contain a YAML mapping at the top level, "
            f"got {type(data).__name__}"
        )
    return HarnessSpec.model_validate(data)
