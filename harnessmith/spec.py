"""HarnessSpec — the minimal spec model that drives generation (Slice 0).

Field names here become the field names of the generated ``config.yaml`` later,
so they are deliberately conservative. Secrets are NEVER stored as values: LLM
profiles reference environment-variable *names* (``api_key_env`` / ``base_url_env``),
and real values live only in ``.env``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_PREFIXES = (
    "sk-",
    "sk_",
    "sk-ant-",
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "github_pat_",
    "gsk_",
    "hf_",
    "xoxb-",
    "xoxp-",
    "glpat-",
)
_REDACTED_ENV_REFERENCE = "<redacted-invalid-env-reference>"
_DISPLAY_NAME_MAX_LENGTH = 120


def is_env_var_name(value: object) -> bool:
    """Return whether ``value`` is an env-var name, not a common secret literal."""
    if not isinstance(value, str) or not ENV_VAR_NAME_RE.fullmatch(value):
        return False
    # Some real credentials also satisfy the identifier grammar (GitHub PATs are
    # the common example), so reject well-known token shapes as a second guardrail.
    if value.startswith(_SECRET_PREFIXES):
        return False
    if re.fullmatch(r"(?:AKIA|ASIA)[A-Z0-9]{16}", value):
        return False
    if value.startswith("AIza") and len(value) >= 32:
        return False
    return True


def _redact_invalid_env_fields(data: Any, fields: tuple[str, ...]) -> Any:
    """Redact bad references before Pydantic copies them into an error object."""
    if not isinstance(data, dict):
        return data
    clean = dict(data)
    for field in fields:
        value = clean.get(field)
        if value is not None and not is_env_var_name(value):
            clean[field] = _REDACTED_ENV_REFERENCE
    return clean


def _validate_env_reference(value: str | None) -> str | None:
    if value is not None and not is_env_var_name(value):
        raise ValueError(
            "must be an environment-variable name "
            "([A-Za-z_][A-Za-z0-9_]*); secret-looking values are rejected"
        )
    return value


class LLMProfile(BaseModel):
    """A named LLM configuration (placeholder in Slice 0; expanded in Slice 1)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    model: str
    # Which API spec this profile speaks (Slice 12). "openai" (default) is the
    # provider-agnostic Chat Completions path via base_url; "anthropic" is the
    # native Anthropic Messages API (first-class thinking/effort). Both clients
    # ship in every product (human decision 2026-06-11: dual protocol built-in);
    # this field just sets the profile's initial value in config.yaml — users
    # switch at runtime via the /config panel or by editing the file.
    provider: Literal["openai", "anthropic"] = "openai"
    api_key_env: str = "OPENAI_API_KEY"
    base_url_env: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _redact_invalid_env_references(cls, data: Any) -> Any:
        return _redact_invalid_env_fields(data, ("api_key_env", "base_url_env"))

    @field_validator("api_key_env", "base_url_env")
    @classmethod
    def _env_references_are_names(cls, value: str | None) -> str | None:
        return _validate_env_reference(value)


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


class Memory(BaseModel):
    """Opt-in cross-session long-term memory (Slice 8B).

    Like :class:`Mcp` / :class:`Skills`, generation-time decides ONLY whether the
    capability exists: ``enabled`` renders ``harness/memory.py`` (a thin
    ``@register_memory`` backend registry with a built-in file backend), the
    memory read/write tools, system-prompt injection, and a ``memory`` block in
    ``config.yaml``. *Which* backend / where the note lives / how much to inject
    are runtime knobs in ``config.yaml`` — not spec fields. Disabled leaves the
    generated repo with zero memory footprint (byte-identical to no-memory).

    Memory is a few self-maintained notes the agent curates on purpose (the agent
    writes them with the memory tools); it is distinct from RAG (external-corpus
    retrieval, v1+). No secrets are ever written — keys stay in ``.env``.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class Subagents(BaseModel):
    """Opt-in multi-agent via subagents (agent-as-tool; the orchestrator-worker
    pattern, the one mature harnesses use — Claude Code's ``Task`` / Anthropic
    Sub-agents / OpenAI agent-as-tool).

    Like :class:`Mcp` / :class:`Skills` / :class:`Memory`, generation-time decides
    ONLY whether the capability exists: ``enabled`` renders ``harness/subagents.py``
    (a single ``subagents`` tool that fans work out to scoped worker agents, in
    parallel, each with its own fresh context, tool allowlist, and model profile),
    seeds an example ``subagents`` block in ``config.yaml``, and injects a short
    "you can delegate" note into the supervisor's system prompt. The roster
    (which workers exist, their prompts / tools / profiles) is a RUNTIME knob in
    ``config.yaml`` — not a spec field. Disabled leaves the generated repo with
    zero subagents footprint.

    The supervisor is just the normal ``agent`` paradigm (it autonomously decides
    when to delegate by calling ``subagents``) — there is NO new paradigm and NO
    change to the core loop. Topology is fixed at depth 1: a worker never gets the
    ``subagents`` tool, so workers cannot spawn further subagents. This stays well
    inside the project's red line (no orchestration framework / DSL / dynamic
    graph): it is plain generated code over a stdlib thread pool.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class Observability(BaseModel):
    """Tracing / cost-accounting settings."""

    model_config = ConfigDict(extra="forbid")

    trace: bool = True
    trace_dir: str = "traces"

    @field_validator("trace_dir")
    @classmethod
    def _trace_dir_is_one_line(cls, value: str) -> str:
        if not value or any(
            unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"}
            for char in value
        ):
            raise ValueError("trace_dir must be a non-empty single-line path")
        return value


class Prompts(BaseModel):
    """System-prompt assembly inputs (consumed by prompts.py in Slice 1)."""

    model_config = ConfigDict(extra="forbid")

    system: str | None = None
    # Always-apply project rule files (the open AGENTS.md / CLAUDE.md / .cursor
    # rules pattern): paths to markdown files whose text is injected into every
    # system prompt. This is only a *seed* for the runtime knob — it is rendered
    # into ``config.yaml`` (``prompts.rules_files``) where it stays editable
    # without regenerating. Empty means no rule files (zero footprint). A listed
    # ``RULES.md`` also gets a starter file generated into the repo.
    rules_files: list[str] = Field(default_factory=list)


class HarnessSpec(BaseModel):
    """Minimal HarnessSpec for Slice 0.

    ``context`` / ``rag`` / ``secrets`` are declared for forward compatibility but
    are not interpreted in Slice 0 — they are passed through untouched.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = "0.1"
    project_slug: str = "agent_harness"
    # Human-readable display name (e.g. "My Coding Assistant"). Used for UI titles
    # (product web header / FastAPI title) and the README heading; falls back to
    # ``project_slug`` when unset. The wizard derives ``project_slug`` from it.
    # It is a label, not a runtime knob — it is never written to ``config.yaml``.
    display_name: str | None = None
    # Default UI language for the generated product's web interface (and the
    # wizard that produced it): "en" or "zh". This is only the baked-in default —
    # the product user can still switch at runtime (the choice is remembered in
    # the browser). It seeds the web UI default, not ``config.yaml``. The agent's
    # *response* language is a separate, optional system-prompt directive the
    # wizard can add (most models already match the user's input language).
    language: Literal["en", "zh"] = "en"
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
    memory: Memory = Field(default_factory=Memory)
    subagents: Subagents = Field(default_factory=Subagents)
    observability: Observability = Field(default_factory=Observability)
    # Per-LLM cost accounting and limits are runtime-only knobs on each profile in
    # config.yaml (``input/output/cached_input_cost_per_million`` + ``cost_limit``),
    # edited on the product's Budget page — there is no spec-level budget block.

    # Context-window management seed (runtime-authoritative — this only seeds the
    # product's config.yaml `context` block). Optional keys: `strategy`
    # (truncate/summarize/none), `keep_last_turns`, `combine` (or/and), and
    # `triggers` (condition name -> threshold, e.g. {"max_tokens": 192000,
    # "max_turns": 40}). Omitted -> the template defaults (summarize, compact at
    # 192k tokens, no turn limit). Behavior lives in config.yaml; this is a seed.
    context: dict[str, Any] | None = None
    # Reserved for later slices: declared so specs stay forward-compatible under
    # extra="forbid", but not interpreted by the current generator.
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

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(
            unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"}
            for char in value
        ):
            raise ValueError("display_name must be a single line without control characters")
        value = value.strip()
        if not value:
            raise ValueError("display_name must not be blank")
        if len(value) > _DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(
                f"display_name must be at most {_DISPLAY_NAME_MAX_LENGTH} characters"
            )
        return value

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
