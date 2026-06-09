"""CLI tests for fast error paths and ``doctor`` (no network / uv / docker)."""

from __future__ import annotations

from typer.testing import CliRunner

from harnessforge.cli import app

runner = CliRunner()


def test_new_requires_exactly_one_source(tmp_path):
    result = runner.invoke(app, ["new", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "exactly one of --spec or --preset" in result.output


def test_new_rejects_both_spec_and_preset(tmp_path):
    result = runner.invoke(
        app,
        ["new", str(tmp_path / "out"), "--spec", "x.yaml", "--preset", "coding-assistant"],
    )
    assert result.exit_code == 2


def test_new_unknown_preset_exits_2(tmp_path):
    result = runner.invoke(
        app, ["new", str(tmp_path / "out"), "--preset", "nope"]
    )
    assert result.exit_code == 2
    assert "Invalid spec" in result.output


def test_new_unknown_mcp_server_exits_2(tmp_path):
    result = runner.invoke(
        app,
        ["new", str(tmp_path / "out"), "--preset", "coding-assistant", "--mcp-server", "nope"],
    )
    assert result.exit_code == 2
    assert "Invalid spec" in result.output


def test_doctor_runs_and_reports_uv():
    result = runner.invoke(app, ["doctor"])
    # uv is installed in this dev environment; doctor should report it.
    assert "uv:" in result.output


def test_wizard_exposes_open_flag():
    """The launch script relies on `wizard --open` to pop the browser."""
    result = runner.invoke(app, ["wizard", "--help"])
    assert result.exit_code == 0
    assert "--open" in result.output
