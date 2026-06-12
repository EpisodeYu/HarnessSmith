"""CLI tests for fast error paths and ``doctor`` (no network / uv / docker)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import harnessmith.cli as cli_mod
from harnessmith.cli import app
from harnessmith.cli_wizard import WizardResult
from harnessmith.generator import GenerationResult
from harnessmith.spec import HarnessSpec

runner = CliRunner()


def test_new_without_source_non_interactive_errors(tmp_path):
    """No --spec/--preset and no terminal -> point the user at a recipe / the
    wizard rather than guessing (CliRunner's stdin is not a tty)."""
    result = runner.invoke(app, ["new", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "Provide --spec or --preset" in result.output


def test_new_no_input_forces_non_interactive(tmp_path):
    """--no-input disables the wizard, so a source becomes mandatory."""
    result = runner.invoke(app, ["new", str(tmp_path / "out"), "--no-input"])
    assert result.exit_code == 2
    assert "Provide --spec or --preset" in result.output


def test_new_help_mentions_no_input():
    result = runner.invoke(app, ["new", "--help"])
    assert result.exit_code == 0
    assert "--no-input" in result.output


def test_new_runs_interactive_wizard_when_no_source(tmp_path, monkeypatch):
    """With a (faked) terminal and no recipe, `new` drives the wizard and feeds its
    spec into generate with the wizard's HITL confirm policy."""
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    out = tmp_path / "wiz_out"
    spec = HarnessSpec(project_slug="demo")
    monkeypatch.setattr(
        cli_mod,
        "run_wizard",
        lambda **k: WizardResult(spec=spec, mcp_servers=[], target_dir=out, confirm_default="high"),
    )
    captured = {}

    def fake_generate(s, td, *, git_init, mcp_servers, confirm_default):
        captured.update(target_dir=Path(td), confirm_default=confirm_default, slug=s.project_slug)
        return GenerationResult(target_dir=Path(td), project_slug=s.project_slug)

    monkeypatch.setattr(cli_mod, "generate", fake_generate)
    monkeypatch.setattr(cli_mod, "lock_dependencies", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "smoke_check", lambda *a, **k: None)

    result = runner.invoke(app, ["new"])
    assert result.exit_code == 0, result.output
    assert captured["target_dir"] == out
    assert captured["confirm_default"] == "high"
    assert captured["slug"] == "demo"


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
