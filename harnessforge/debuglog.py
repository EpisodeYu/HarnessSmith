"""Always-on local debug log for the generator itself.

Every harnessforge invocation (CLI, wizard) appends to
``~/.harnessforge/logs/debug.log`` (rotating at ~1 MB; override the directory
with ``HARNESSFORGE_LOG_DIR``). The point is post-hoc diagnosis: when a
generation / smoke check / wizard launch fails, the log shows which phase broke
and why, without asking the user to re-run with a flag.

Local-only by contract: the file is never uploaded, never copied into a
generated repo, and records phases / file names / command lines / durations /
errors — not spec free text and never secret values (the generator never sees
secrets in the first place).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("harnessforge")
log.addHandler(logging.NullHandler())  # silent unless setup() attaches a file

LOG_DIR_ENV = "HARNESSFORGE_LOG_DIR"
LOG_FILE_NAME = "debug.log"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _log_dir() -> Path:
    override = os.environ.get(LOG_DIR_ENV)
    return Path(override) if override else Path.home() / ".harnessforge" / "logs"


def setup() -> Path | None:
    """Attach (or re-point) the rotating file handler; return the log path.

    Idempotent and re-entrant: any existing file handler is replaced, so a
    changed ``HARNESSFORGE_LOG_DIR`` (tests) takes effect on the next call.
    Best-effort — an unwritable directory degrades to no file log (``None``)
    rather than ever breaking a generation.
    """
    for handler in list(log.handlers):
        if isinstance(handler, RotatingFileHandler):
            log.removeHandler(handler)
            handler.close()
    try:
        directory = _log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / LOG_FILE_NAME
        handler = RotatingFileHandler(
            path, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter(_FORMAT))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    return path
