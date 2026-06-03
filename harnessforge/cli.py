"""HarnessForge CLI: ``new`` generates a runnable harness; ``doctor`` pre-flights.

``new`` renders a spec (from ``--spec`` or ``--preset``) into an owned repo, locks
its dependencies (``uv.lock`` + ``requirements.txt``), and smoke-tests that the
result actually runs. ``--no-verify`` skips the smoke check (the lock still runs
so the repo ships a deterministic dependency set).
"""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from .generator import (
    SmokeCheckError,
    TargetExistsError,
    ToolingError,
    doctor as run_doctor,
    generate,
    lock_dependencies,
    smoke_check,
)
from .presets import PresetNotFoundError, available_presets, preset_spec_path
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
    spec: Path | None = typer.Option(
        None, "--spec", "-s", help="Path to a HarnessSpec YAML file."
    ),
    preset: str | None = typer.Option(
        None,
        "--preset",
        "-p",
        help=f"Use a bundled preset instead of --spec ({', '.join(available_presets())}).",
    ),
    git_init: bool = typer.Option(
        True, "--git/--no-git", help="Run 'git init' in the generated repo."
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Smoke-test the generated repo (uv sync + import + mock + pytest).",
    ),
) -> None:
    """Generate a new agent harness repo from a spec or preset."""
    if (spec is None) == (preset is None):
        typer.secho(
            "Provide exactly one of --spec or --preset.", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=2)

    try:
        spec_path = preset_spec_path(preset) if preset else spec
        harness_spec = load_spec(spec_path)
    except (FileNotFoundError, ValueError, ValidationError, PresetNotFoundError) as exc:
        typer.secho(f"Invalid spec: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    try:
        result = generate(harness_spec, target_dir, git_init=git_init)
    except TargetExistsError as exc:
        typer.secho(f"Skipped (no overwrite): {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)

    typer.secho(
        f"Generated '{result.project_slug}' at {result.target_dir} "
        f"({len(result.written_files)} files"
        f"{', git initialized' if result.git_initialized else ''}).",
        fg=typer.colors.GREEN,
    )

    try:
        typer.echo("Locking dependencies (uv lock + requirements.txt) ...")
        lock_dependencies(result.target_dir)
        if verify:
            typer.echo("Smoke-testing the generated repo ...")
            smoke_check(result.target_dir, result.project_slug)
    except SmokeCheckError as exc:
        typer.secho(f"Smoke check failed:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)
    except ToolingError as exc:
        typer.secho(f"Tooling error:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)

    if verify:
        typer.secho("Verified runnable.", fg=typer.colors.GREEN)
    typer.echo(
        f"\nNext:\n  cd {result.target_dir}\n"
        f"  uv run {result.project_slug} run --mock \"hello\""
    )


@app.command()
def doctor() -> None:
    """Pre-flight: check that uv is installed and the package index is reachable."""
    report = run_doctor()
    uv_line = f"uv: {report.uv_version}" if report.uv_ok else "uv: NOT FOUND"
    net_line = "network: ok" if report.network_ok else "network: unreachable"
    color = typer.colors.GREEN if report.healthy else typer.colors.YELLOW
    typer.secho(uv_line, fg=color)
    typer.secho(net_line, fg=color)
    for note in report.notes:
        typer.secho(f"  - {note}", fg=typer.colors.YELLOW)
    if not report.healthy:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
