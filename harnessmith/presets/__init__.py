"""Built-in HarnessSmith presets — ready-to-generate example specs."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..catalog import CatalogServer, resolve_servers

PRESETS_DIR = Path(__file__).parent
MCP_PREFILL_NAME = "mcp_prefill.yaml"


class PresetNotFoundError(Exception):
    """Raised when a named preset does not exist."""


def available_presets() -> list[str]:
    """Names of bundled presets (directories containing a ``spec.yaml``)."""
    return sorted(
        child.name
        for child in PRESETS_DIR.iterdir()
        if child.is_dir() and (child / "spec.yaml").is_file()
    )


def preset_spec_path(name: str) -> Path:
    """Resolve a preset name to its ``spec.yaml`` path."""
    path = PRESETS_DIR / name / "spec.yaml"
    if not path.is_file():
        known = ", ".join(available_presets()) or "(none)"
        raise PresetNotFoundError(
            f"unknown preset {name!r}; available presets: {known}"
        )
    return path


def preset_mcp_servers(name: str) -> list[CatalogServer]:
    """Resolve a preset's optional MCP prefill into catalog servers.

    The prefill (``<preset>/mcp_prefill.yaml``) is a generation-time convenience
    that names which catalog servers to write into the generated ``config.yaml``;
    it is NOT part of the spec/snapshot. Returns ``[]`` when the preset has none.
    """
    path = PRESETS_DIR / name / MCP_PREFILL_NAME
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return resolve_servers(list(data.get("servers") or []))
