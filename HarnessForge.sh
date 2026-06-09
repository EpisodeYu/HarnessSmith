#!/usr/bin/env bash
# One-click launcher for the HarnessForge wizard.
#
# Opens the spec wizard in your browser. Prefers `uv` (which auto-syncs the
# optional [wizard] extra); if uv is missing it offers to install it (user-level,
# no root).
set -e
cd "$(dirname "$0")"

find_uv() {
  if command -v uv >/dev/null 2>&1; then echo uv; return 0; fi
  [ -x "$HOME/.local/bin/uv" ] && { echo "$HOME/.local/bin/uv"; return 0; }
  return 1
}

uv_bin="$(find_uv || true)"
if [ -z "$uv_bin" ]; then
  # No uv yet: an already-installed harnessforge command works too.
  if command -v harnessforge >/dev/null 2>&1; then
    exec harnessforge wizard --open
  fi
  echo
  echo "  The HarnessForge wizard needs uv - a small, self-contained tool that manages"
  echo "  Python and dependencies for you (user-level install, no root)."
  printf "  Install uv now? [Y/n] "
  read -r reply </dev/tty 2>/dev/null || reply=Y
  case "$reply" in
    [Nn]*) ;;
    *) curl -LsSf https://astral.sh/uv/install.sh | sh \
         || echo "  uv install failed; see https://docs.astral.sh/uv/" >&2 ;;
  esac
  uv_bin="$(find_uv || true)"
fi

if [ -n "$uv_bin" ]; then
  exec "$uv_bin" run --extra wizard harnessforge wizard --open
fi

echo "  Could not find or install uv. Install it (user-level, no root):" >&2
echo "    curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
echo "  then re-run this script." >&2
exit 1
