"""HarnessSmith CLI: ``new`` generates a runnable harness; ``doctor`` pre-flights.

``new`` renders a spec (from ``--spec`` or ``--preset``) into an owned repo, locks
its dependencies (``uv.lock`` + ``requirements.txt``), and smoke-tests that the
result actually runs. ``--no-verify`` skips the smoke check (the lock still runs
so the repo ships a deterministic dependency set).
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import typer
from pydantic import ValidationError

from .catalog import CatalogError, available_servers, resolve_servers
from .cli_wizard import WizardAborted, run_wizard
from .debuglog import log, setup as setup_debug_log
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
    help="HarnessSmith — forge your own agent harness.",
    epilog=(
        "Tip: the web wizard is the easiest way to start.\n\n"
        'From PyPI, no install:  uvx --from "harnessmith\\[wizard]" '
        "harnessmith wizard --open\n\n"
        "Already installed:  harnessmith wizard --open"
    ),
)


def _stdin_is_tty() -> bool:
    """True when stdin is an interactive terminal (so the wizard can prompt).

    A tiny indirection that keeps the tty check monkeypatchable in tests."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


@app.callback()
def _main() -> None:
    """HarnessSmith — forge your own agent harness."""
    setup_debug_log()
    log.debug("invoked: %s", sys.argv[1:])


@app.command()
def new(
    target_dir: Path | None = typer.Argument(
        None,
        help="Directory to create the generated harness repo in "
        "(the interactive wizard prompts for it when omitted).",
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
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-input",
        help="Use the interactive setup wizard when no --spec/--preset is given "
        "(auto-off when stdin is not a terminal; --no-input forces it off).",
    ),
) -> None:
    """Generate a new agent harness repo from a spec, preset, or the interactive wizard."""
    if spec is not None and preset is not None:
        typer.secho(
            "Provide exactly one of --spec or --preset.", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=2)

    # No recipe given: drop into the interactive wizard if we have a terminal,
    # otherwise tell the user how to feed one (keeps scripts / CI explicit).
    use_wizard = spec is None and preset is None and interactive and _stdin_is_tty()
    if spec is None and preset is None and not use_wizard:
        typer.secho(
            "Provide --spec or --preset, or run in an interactive terminal to use "
            "the setup wizard.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    confirm_default = "none"
    if use_wizard:
        try:
            wiz = run_wizard(default_target_dir=str(target_dir) if target_dir else None)
        except WizardAborted as exc:
            typer.secho(f"Setup wizard cancelled: {exc}", fg=typer.colors.YELLOW, err=True)
            raise typer.Exit(code=1)
        harness_spec = wiz.spec
        mcp_servers = wiz.mcp_servers
        confirm_default = wiz.confirm_default
        target_dir = target_dir or wiz.target_dir
    else:
        if target_dir is None:
            typer.secho(
                "Missing TARGET_DIR (the directory to generate into).",
                fg=typer.colors.RED,
                err=True,
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
            log.debug("new: invalid spec (%s: %s)", type(exc).__name__, exc)
            typer.secho(f"Invalid spec: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
    log.debug(
        "new: spec loaded (slug=%s preset=%s web=%s mcp=%s skills=%s memory=%s "
        "paradigms=%s mcp_prefill=%s)",
        harness_spec.project_slug, preset, harness_spec.interfaces.web,
        harness_spec.mcp.enabled, harness_spec.skills.enabled,
        harness_spec.memory.enabled, harness_spec.paradigms,
        [s.name for s in mcp_servers],
    )

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
            harness_spec,
            target_dir,
            git_init=git_init,
            mcp_servers=mcp_servers,
            confirm_default=confirm_default,
        )
    except TargetExistsError as exc:
        log.debug("new: target exists, refused (%s)", exc)
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
        log.debug("new: smoke check FAILED:\n%s", exc)
        typer.secho(f"Smoke check failed:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)
    except ToolingError as exc:
        log.debug("new: tooling error:\n%s", exc)
        typer.secho(f"Tooling error:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)

    if verify:
        log.debug("new: verified runnable at %s", result.target_dir)
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


def _open_browser_when_ready(url: str, host: str, port: int) -> None:
    """Open ``url`` in the default browser once the server accepts connections.

    Runs in a background thread so it can wait out uvicorn's startup without
    blocking the (blocking) ``uvicorn.run`` call. Best-effort: a headless box
    with no browser simply no-ops.
    """
    connect_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host

    def _wait_and_open() -> None:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.25)
                if sock.connect_ex((connect_host, port)) == 0:
                    break
            time.sleep(0.15)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_wait_and_open, daemon=True).start()


def _maybe_print_forward_hint(port: int) -> None:
    """On Linux, print an SSH port-forward command (the wizard may be remote).

    Local Windows/macOS access is direct, so no hint there. Linux users running
    behind SSH can copy this to reach the port from their own machine.
    """
    if not sys.platform.startswith("linux"):
        return
    typer.secho(
        "  remote? forward this port from your machine:\n"
        f"    ssh -L {port}:127.0.0.1:{port} <user>@<host>",
        fg=typer.colors.BRIGHT_BLACK,
    )


@app.command()
def wizard(
    host: str = typer.Option("127.0.0.1", help="Host to bind the wizard to."),
    port: int = typer.Option(
        0, "--port", help="Port to bind to; 0 (default) auto-picks a free port from 8000."
    ),
    open_browser: bool = typer.Option(
        False,
        "--open/--no-open",
        help="Open the wizard in your default browser once it starts.",
    ),
) -> None:
    """Launch the single-page spec wizard (needs the optional `wizard` extra)."""
    try:
        import uvicorn

        from .wizard.app import create_app
    except ImportError as exc:
        typer.secho(
            "The wizard needs its optional dependencies. Install them with:\n"
            "  uv pip install 'harnessmith[wizard]'  (or pip install 'harnessmith[wizard]')",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    bind_port = port if port else _find_free_port(8000, host=host)
    log.debug("wizard: serving on %s:%s (open_browser=%s)", host, bind_port, open_browser)
    typer.secho(
        f"HarnessSmith wizard → http://{host}:{bind_port}  (open this; Ctrl-C to stop)",
        fg=typer.colors.GREEN,
    )
    _maybe_print_forward_hint(bind_port)
    if open_browser:
        _open_browser_when_ready(f"http://{host}:{bind_port}", host, bind_port)
    uvicorn.run(create_app(), host=host, port=bind_port)


@app.command()
def doctor() -> None:
    """Pre-flight: check that uv is installed and the package index is reachable."""
    report = run_doctor()
    log.debug(
        "doctor: uv_ok=%s (%s) network_ok=%s notes=%s",
        report.uv_ok, report.uv_version, report.network_ok, report.notes,
    )
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
