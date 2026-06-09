#!/usr/bin/env bash
# One-click launcher for the HarnessForge wizard.
#
# Opens the spec wizard in your browser. Prefers `uv` (which auto-syncs the
# optional [wizard] extra) and falls back to an installed `harnessforge` command.
set -e
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  exec uv run --extra wizard harnessforge wizard --open
elif command -v harnessforge >/dev/null 2>&1; then
  exec harnessforge wizard --open
else
  echo "Could not find 'uv' or 'harnessforge' on your PATH." >&2
  echo "Install uv (https://docs.astral.sh/uv/) and run this from the repo, or" >&2
  echo "pip install 'harnessforge[wizard]' then run 'harnessforge wizard --open'." >&2
  exit 1
fi
