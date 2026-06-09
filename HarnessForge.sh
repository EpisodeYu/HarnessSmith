#!/usr/bin/env bash
# One-click launcher for the HarnessForge wizard.
#
# Opens the spec wizard in your browser. Prefers `uv` (which auto-syncs the
# optional [wizard] extra); if uv is missing it offers to install it (user-level,
# no root).
set -e
echo "[HarnessForge] Wizard launcher"
cd "$(dirname "$0")"
echo "[HarnessForge] Folder: $PWD"

find_uv() {
  if command -v uv >/dev/null 2>&1; then echo uv; return 0; fi
  [ -x "$HOME/.local/bin/uv" ] && { echo "$HOME/.local/bin/uv"; return 0; }
  return 1
}

echo "[HarnessForge] Looking for uv ..."
uv_bin="$(find_uv || true)"
if [ -z "$uv_bin" ]; then
  # No uv yet: an already-installed harnessforge command works too.
  if command -v harnessforge >/dev/null 2>&1; then
    echo "[HarnessForge] Found the harnessforge command; launching ..."
    exec harnessforge wizard --open
  fi
  echo "[HarnessForge] uv is not installed yet. How would you like to install it?"
  echo "    [1] Standard - official installer (downloads from GitHub)"
  echo "    [2] China mirror - pip + Tsinghua mirror (needs python3 already installed)"
  echo "    [n] Don't install"
  printf "  Choose [1/2/n]: "
  read -r choice </dev/tty 2>/dev/null || choice=1
  case "$choice" in
    [Nn]*) ;;
    2)
      if command -v python3 >/dev/null 2>&1; then py=python3
      elif command -v python >/dev/null 2>&1; then py=python
      else py=; fi
      if [ -n "$py" ]; then
        echo "[HarnessForge] Installing uv via pip + Tsinghua mirror ..."
        "$py" -m pip install --user uv -i https://pypi.tuna.tsinghua.edu.cn/simple || true
        if "$py" -m uv --version >/dev/null 2>&1; then
          export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
          export UV_PYTHON_PREFERENCE=only-system
          echo "[HarnessForge] Launching: $py -m uv run --extra wizard harnessforge wizard --open"
          exec "$py" -m uv run --extra wizard harnessforge wizard --open
        fi
      fi
      echo "[HarnessForge] China path needs python3 first (then: pip install uv -i <Tsinghua>)." >&2
      ;;
    *)
      echo "[HarnessForge] Installing uv via the official installer ..."
      curl -LsSf https://astral.sh/uv/install.sh | sh \
        || echo "[HarnessForge] uv install failed; see https://docs.astral.sh/uv/" >&2 ;;
  esac
  uv_bin="$(find_uv || true)"
fi

if [ -n "$uv_bin" ]; then
  echo "[HarnessForge] Launching: $uv_bin run --extra wizard harnessforge wizard --open"
  exec "$uv_bin" run --extra wizard harnessforge wizard --open
fi

echo "[HarnessForge] Could not find or install uv. Install it (user-level, no root):" >&2
echo "    curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
echo "    - or (China) -  pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple" >&2
echo "  then re-run this script." >&2
exit 1
