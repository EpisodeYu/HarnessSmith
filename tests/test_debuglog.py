"""The generator's always-on local debug log (harnessforge/debuglog.py)."""

from __future__ import annotations

from logging.handlers import RotatingFileHandler

import pytest
from typer.testing import CliRunner

from harnessforge import debuglog
from harnessforge.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    """Point the log at a temp dir for the test, then detach the handler."""
    monkeypatch.setenv(debuglog.LOG_DIR_ENV, str(tmp_path / "hf-logs"))
    yield tmp_path / "hf-logs"
    for handler in list(debuglog.log.handlers):
        if isinstance(handler, RotatingFileHandler):
            debuglog.log.removeHandler(handler)
            handler.close()


def test_setup_writes_to_env_override_dir(isolated_log):
    path = debuglog.setup()
    assert path == isolated_log / debuglog.LOG_FILE_NAME
    debuglog.log.debug("hello from the test")
    assert "hello from the test" in path.read_text(encoding="utf-8")


def test_setup_is_idempotent(isolated_log):
    debuglog.setup()
    debuglog.setup()
    handlers = [
        h for h in debuglog.log.handlers if isinstance(h, RotatingFileHandler)
    ]
    assert len(handlers) == 1


def test_cli_logs_invocation_and_spec_errors(isolated_log, tmp_path):
    result = runner.invoke(app, ["new", str(tmp_path / "out"), "--preset", "nope"])
    assert result.exit_code == 2
    text = (isolated_log / debuglog.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "invoked:" in text
    assert "invalid spec" in text


def test_generate_logs_render_phases(isolated_log, tmp_path):
    from harnessforge.generator import generate
    from harnessforge.presets import preset_spec_path
    from harnessforge.spec import load_spec

    debuglog.setup()
    spec = load_spec(preset_spec_path("coding-assistant"))
    generate(spec, tmp_path / "out", git_init=False)
    text = (isolated_log / debuglog.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "generate: render config.yaml.j2" in text
    assert "generate: wrote" in text
