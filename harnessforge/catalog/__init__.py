"""Static MCP server catalog — a generation-time convenience datasource (Slice 6).

Loaded by ``harnessforge new --mcp-server <name>`` and by presets to PREFILL the
generated repo's runtime ``config.yaml`` (``mcp.servers`` + the tool allowlist).
It is **not** a security gate and is **not** part of :class:`HarnessSpec` or its
snapshot — the real gate is the runtime allowlist + per-tool risk markers.
Secrets are referenced by env-var NAME only, never stored as values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).parent / "mcp_servers.yaml"

SAFE = "safe"
HIGH = "high"


class CatalogError(Exception):
    """Raised when the catalog file or a requested server is invalid/missing."""


@dataclass(frozen=True)
class CatalogTool:
    name: str
    risk: str = HIGH
    default_enabled: bool = False


@dataclass(frozen=True)
class CatalogServer:
    """One curated MCP server entry (transport + tools + provenance)."""

    name: str
    description: str = ""
    transport: str = "stdio"  # "stdio" | "remote"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    url: str | None = None
    auth_env: str | None = None
    requires: str | None = None  # runtime prerequisite: "uv" | "node" | None
    source: str = ""
    updated: str = ""
    tools: list[CatalogTool] = field(default_factory=list)

    @property
    def safe_tools(self) -> list[str]:
        """Unprefixed names of read-only/low-risk tools (offered to plan/ask)."""
        return [t.name for t in self.tools if t.risk == SAFE]

    @property
    def uvx_package(self) -> str | None:
        """The pip/uvx package name for a uvx-launched server (else ``None``)."""
        if self.command == "uvx" and self.args:
            return self.args[0]
        return None

    def server_entry(self) -> dict:
        """A ``config.yaml`` ``mcp.servers`` entry (env-var NAMES only)."""
        entry: dict = {"name": self.name}
        if self.command:
            entry["command"] = self.command
            entry["args"] = list(self.args)
            if self.env:
                entry["env"] = list(self.env)
        else:
            entry["url"] = self.url
            if self.auth_env:
                entry["auth_env"] = self.auth_env
        if self.safe_tools:
            entry["safe_tools"] = self.safe_tools
        return entry

    def allowlist_entries(self) -> list[dict]:
        """``config.yaml`` ``tools`` entries (``<server>__<tool>`` + default state)."""
        return [
            {"name": f"{self.name}__{tool.name}", "enabled": tool.default_enabled}
            for tool in self.tools
        ]


def _coerce_server(name: str, data: dict) -> CatalogServer:
    tools = [
        CatalogTool(
            name=t["name"],
            risk=t.get("risk", HIGH),
            default_enabled=bool(t.get("default_enabled", False)),
        )
        for t in (data.get("tools") or [])
    ]
    return CatalogServer(
        name=name,
        description=data.get("description", ""),
        transport=data.get("transport", "stdio"),
        command=data.get("command"),
        args=list(data.get("args") or []),
        env=list(data.get("env") or []),
        url=data.get("url"),
        auth_env=data.get("auth_env"),
        requires=data.get("requires"),
        source=data.get("source", ""),
        updated=str(data.get("updated", "")),
        tools=tools,
    )


def load_catalog(path: str | Path = CATALOG_PATH) -> dict[str, CatalogServer]:
    """Load the catalog into a name -> :class:`CatalogServer` mapping."""
    path = Path(path)
    if not path.exists():
        raise CatalogError(f"catalog file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = data.get("servers") or {}
    if not isinstance(servers, dict):
        raise CatalogError("catalog 'servers' must be a mapping of name -> entry")
    return {name: _coerce_server(name, entry) for name, entry in servers.items()}


def available_servers() -> list[str]:
    """Names of curated catalog servers."""
    return sorted(load_catalog())


def get_server(name: str) -> CatalogServer:
    """Resolve a catalog server by name (raises :class:`CatalogError`)."""
    catalog = load_catalog()
    if name not in catalog:
        known = ", ".join(sorted(catalog)) or "(none)"
        raise CatalogError(f"unknown MCP server {name!r}; catalog has: {known}")
    return catalog[name]


def resolve_servers(names: list[str]) -> list[CatalogServer]:
    """Resolve catalog server names, de-duplicated, preserving first-seen order."""
    catalog = load_catalog()
    resolved: list[CatalogServer] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        if name not in catalog:
            known = ", ".join(sorted(catalog)) or "(none)"
            raise CatalogError(f"unknown MCP server {name!r}; catalog has: {known}")
        resolved.append(catalog[name])
        seen.add(name)
    return resolved
