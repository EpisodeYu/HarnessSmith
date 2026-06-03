"""Built-in HarnessForge presets — ready-to-generate example specs."""

from __future__ import annotations

from pathlib import Path

PRESETS_DIR = Path(__file__).parent


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
