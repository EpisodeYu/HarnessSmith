"""HarnessForge CLI: ``new`` generates a runnable harness; ``doctor`` pre-flights.

``new`` renders a spec (from ``--spec`` or ``--preset``) into an owned repo, locks
its dependencies (``uv.lock`` + ``requirements.txt``), and smoke-tests that the
result actually runs. ``--no-verify`` skips the smoke check (the lock still runs
so the repo ships a deterministic dependency set).
"""

from __future__ import annotations

import socket
from pathlib import Path

import typer
from pydantic import ValidationError

from .catalog import CatalogError, available_servers, resolve_servers
from .generator import (
    SmokeCheckError,
    TargetExistsError,
    ToolingError,
    doctor as run_doctor,
    generate,
    lock_dependencies,
    prewarm_mcp_servers,
    smoke_check,
)
from .presets import (
    PresetNotFoundError,
    available_presets,
    preset_mcp_servers,
    preset_spec_path,
)
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
    mcp_server: list[str] = typer.Option(
        [],
        "--mcp-server",
        help=(
            "Prefill an MCP server from the catalog into config.yaml (repeatable). "
            f"Catalog: {', '.join(available_servers())}."
        ),
    ),
    git_init: bool = typer.Option(
        True, "--git/--no-git", help="Run 'git init' in the generated repo."
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Smoke-test the generated repo (uv sync + import + mock + pytest).",
    ),
    prewarm: bool = typer.Option(
        True,
        "--prewarm/--no-prewarm",
        help="Warm the uv cache for uvx-based MCP servers (offline-ready first run).",
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
        # MCP prefill = preset's baseline + any explicit --mcp-server (catalog).
        mcp_servers = preset_mcp_servers(preset) if preset else []
        if mcp_server:
            mcp_servers = mcp_servers + resolve_servers(list(mcp_server))
    except (
        FileNotFoundError,
        ValueError,
        ValidationError,
        PresetNotFoundError,
        CatalogError,
    ) as exc:
        typer.secho(f"Invalid spec: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if mcp_servers and not harness_spec.mcp.enabled:
        typer.secho(
            "Ignoring --mcp-server: spec has mcp.enabled = false (set it to true to "
            "prefill servers).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        mcp_servers = []

    try:
        result = generate(
            harness_spec, target_dir, git_init=git_init, mcp_servers=mcp_servers
        )
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
        if prewarm and any(s.uvx_package for s in mcp_servers):
            typer.echo("Prewarming uvx MCP servers (uv cache) ...")
            warmed = prewarm_mcp_servers(mcp_servers)
            if warmed:
                typer.secho(f"  cached: {', '.join(warmed)}", fg=typer.colors.BRIGHT_BLACK)
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


def _find_free_port(preferred: int, *, host: str = "127.0.0.1", tries: int = 64) -> int:
    """Return a bindable port: try ``preferred`` upward, else an OS-assigned one."""
    for candidate in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


@app.command()
def wizard(
    host: str = typer.Option("127.0.0.1", help="Host to bind the wizard to."),
    port: int = typer.Option(
        0, "--port", help="Port to bind to; 0 (default) auto-picks a free port from 8000."
    ),
) -> None:
    """Launch the single-page spec wizard (needs the optional `wizard` extra)."""
    try:
        import uvicorn

        from .wizard.app import create_app
    except ImportError as exc:
        typer.secho(
            "The wizard needs its optional dependencies. Install them with:\n"
            "  uv pip install 'harnessforge[wizard]'  (or pip install 'harnessforge[wizard]')",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    bind_port = port if port else _find_free_port(8000, host=host)
    typer.secho(
        f"HarnessForge wizard → http://{host}:{bind_port}  (open this; Ctrl-C to stop)",
        fg=typer.colors.GREEN,
    )
    uvicorn.run(create_app(), host=host, port=bind_port)


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
