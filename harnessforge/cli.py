"""HarnessForge CLI (Slice 0): ``harnessforge new <dir> --spec <spec.yaml>``."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from .generator import TargetExistsError, generate
from .spec import load_spec

app = typer.Typer(
    add_completion=False,
    help="HarnessForge — forge your own agent harness (no agent-framework lock-in).",
)


@app.callback()
def _main() -> None:
    """HarnessForge — forge your own agent harness (no agent-framework lock-in)."""


@app.command()
def new(
    target_dir: Path = typer.Argument(
        ...,
        help="Directory to create the generated harness repo in.",
    ),
    spec: Path = typer.Option(
        ...,
        "--spec",
        "-s",
        help="Path to a HarnessSpec YAML file.",
    ),
    git_init: bool = typer.Option(
        True,
        "--git/--no-git",
        help="Run 'git init' in the generated repo.",
    ),
) -> None:
    """Generate a new agent harness repo from a spec."""
    try:
        harness_spec = load_spec(spec)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        typer.secho(f"Invalid spec: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    try:
        result = generate(harness_spec, target_dir, git_init=git_init)
    except TargetExistsError as exc:
        typer.secho(f"Skipped (no overwrite): {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)

    typer.secho(
        f"Generated '{harness_spec.project_slug}' at {result.target_dir} "
        f"({len(result.written_files)} files"
        f"{', git initialized' if result.git_initialized else ''}).",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
