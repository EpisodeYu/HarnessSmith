#!/usr/bin/env bash
# One-click launcher for the HarnessSmith setup wizard.
#
# Lets you pick how to configure your harness: the Web form (opens in a browser)
# or an interactive CLI wizard (right here in the terminal). Prefers `uv` (which
# auto-syncs the optional [wizard] extra for the web form); if uv is missing it
# offers to install it (user-level, no root).
set -e
echo "[HarnessSmith] Setup launcher"
cd "$(dirname "$0")"
echo "[HarnessSmith] Folder: $PWD"

find_uv() {
  if command -v uv >/dev/null 2>&1; then echo uv; return 0; fi
  [ -x "$HOME/.local/bin/uv" ] && { echo "$HOME/.local/bin/uv"; return 0; }
  return 1
}

# Web form vs interactive CLI wizard. On a headless Linux box (no display) the
# terminal wizard is the sensible default — the web form would only be reachable
# via SSH port-forward; elsewhere the browser form is the default. Echoes "web"
# or "cli" on stdout (prompts go to stderr). Set HARNESSMITH_MODE=web|cli to
# skip the prompt (e.g. for automation).
choose_mode() {
  if [ -n "${HARNESSMITH_MODE:-}" ]; then echo "$HARNESSMITH_MODE"; return 0; fi
  default=web
  if [ "$(uname)" = Linux ] && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    default=cli
  fi
  {
    echo "[HarnessSmith] How do you want to set up your harness?"
    echo "    [1] Web wizard - fill a form in your browser"
    echo "    [2] CLI wizard - interactive setup here in the terminal"
    printf "  Choose [1/2] (Enter = %s): " "$default"
  } >&2
  read -r reply </dev/tty 2>/dev/null || reply=""
  case "$reply" in
    1) echo web ;;
    2) echo cli ;;
    *) echo "$default" ;;
  esac
}

# Auto-pick the package index: when no index is pinned and the official PyPI is
# unreachable (e.g. behind the GFW), use the Tsinghua mirror for this run so the
# first `uv sync` can still fetch deps. An explicit UV_DEFAULT_INDEX always wins;
# we only probe when curl is available.
pick_index() {
  [ -n "${UV_DEFAULT_INDEX:-}" ] && return 0
  command -v curl >/dev/null 2>&1 || return 0
  echo "[HarnessSmith] Checking whether PyPI is reachable ..."
  if curl -sS -m 3 -I https://pypi.org/simple/ >/dev/null 2>&1; then return 0; fi
  echo "[HarnessSmith] PyPI looks unreachable - using the Tsinghua mirror this run."
  export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
}

# Reuse the system proxy so the curl probe above, the uv install, and uv's sync all
# reach the net the same way. Only when none is already set. macOS's GUI proxy isn't
# read by curl/uv on their own, so on a Mac we read it via scutil and export it
# (Linux users set *_PROXY as usual -> this is a no-op there). Best-effort: any parse
# miss just leaves the env untouched. Mirrors the wizard's proxy-aware urllib probe.
pick_proxy() {
  [ -n "${HTTP_PROXY:-}${HTTPS_PROXY:-}${http_proxy:-}${https_proxy:-}" ] && return 0
  [ "$(uname)" = Darwin ] || return 0
  command -v scutil >/dev/null 2>&1 || return 0
  local enabled host port px
  enabled="$(scutil --proxy 2>/dev/null | awk '/^[[:space:]]*HTTPSEnable/ {print $3}')"
  [ "$enabled" = 1 ] || return 0
  host="$(scutil --proxy 2>/dev/null | awk '/^[[:space:]]*HTTPSProxy/ {print $3}')"
  [ -n "$host" ] || return 0
  port="$(scutil --proxy 2>/dev/null | awk '/^[[:space:]]*HTTPSPort/ {print $3}')"
  px="http://$host"
  [ -n "$port" ] && px="$px:$port"
  export HTTP_PROXY="$px" HTTPS_PROXY="$px"
  echo "[HarnessSmith] Using system proxy: $px"
}

pick_proxy

echo "[HarnessSmith] Looking for uv ..."
uv_bin="$(find_uv || true)"
if [ -z "$uv_bin" ]; then
  # No uv yet: an already-installed harnessmith command works too.
  if command -v harnessmith >/dev/null 2>&1; then
    echo "[HarnessSmith] Found the harnessmith command."
    if [ "$(choose_mode)" = cli ]; then
      echo "[HarnessSmith] Launching: harnessmith new"
      exec harnessmith new
    fi
    echo "[HarnessSmith] Launching: harnessmith wizard --open"
    exec harnessmith wizard --open
  fi
  echo "[HarnessSmith] uv is not installed yet. How would you like to install it?"
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
        echo "[HarnessSmith] Installing uv via pip + Tsinghua mirror ..."
        "$py" -m pip install --user uv -i https://pypi.tuna.tsinghua.edu.cn/simple || true
        if "$py" -m uv --version >/dev/null 2>&1; then
          export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
          export UV_PYTHON_PREFERENCE=only-system
          echo "[HarnessSmith] Launching: $py -m uv run --extra wizard harnessmith wizard --open"
          exec "$py" -m uv run --extra wizard harnessmith wizard --open
        fi
      fi
      echo "[HarnessSmith] China path needs python3 first (then: pip install uv -i <Tsinghua>)." >&2
      ;;
    *)
      echo "[HarnessSmith] Installing uv via the official installer ..."
      curl -LsSf https://astral.sh/uv/install.sh | sh \
        || echo "[HarnessSmith] uv install failed; see https://docs.astral.sh/uv/" >&2 ;;
  esac
  uv_bin="$(find_uv || true)"
fi

if [ -n "$uv_bin" ]; then
  pick_index
  if [ "$(choose_mode)" = cli ]; then
    echo "[HarnessSmith] Launching: $uv_bin run harnessmith new"
    exec "$uv_bin" run harnessmith new
  fi
  echo "[HarnessSmith] Launching: $uv_bin run --extra wizard harnessmith wizard --open"
  exec "$uv_bin" run --extra wizard harnessmith wizard --open
fi

echo "[HarnessSmith] Could not find or install uv. Install it (user-level, no root):" >&2
echo "    curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
echo "    - or (China) -  pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple" >&2
echo "  then re-run this script." >&2
exit 1
