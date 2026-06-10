"""Provision a user-local portable Node.js for Node-based MCP servers.

Desktop Commander (and other ``npx`` servers) need a Node runtime, which a typical
Windows box lacks. The product launch scripts (``<slug>.bat``/``.sh``) offer to
fetch a portable Node in shell; this is the Python twin used by the wizard's
*headless* one-click launch (which runs ``uv run <slug> serve`` directly and so
never executes those scripts). Node is downloaded on demand into a user-local
directory — the SAME location the launch scripts use, so the two share — and is
never bundled into the generated repo. A pinned LTS keeps the URL stable.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

NODE_LTS_VERSION = "v22.11.0"
_NODE_OFFICIAL = "https://nodejs.org/dist"
_NODE_MIRROR = "https://npmmirror.com/mirrors/node"  # domestic mirror (GFW)

# Fallback is for a DEAD source, never a slow one: only a stall (no data within the
# per-read socket timeout) or an outright connection/HTTP failure moves to the next
# source. A slow-but-steady transfer is ridden to completion — a slow success beats
# a fast failure (and never strands a user who switched off a working-but-slow
# source onto a mirror that then can't connect). Source ORDER (mirror-first behind
# the GFW) is what avoids the slow path up front, not abandoning sources mid-flight.
_READ_TIMEOUT = 60.0
_CHUNK = 1 << 16


def node_on_path() -> bool:
    """True when both ``node`` and ``npx`` are already resolvable on PATH."""
    return bool(shutil.which("node") and shutil.which("npx"))


def _platform_tag() -> tuple[str, str, str] | None:
    """``(nodeos, nodearch, ext)`` for this host, or ``None`` if unsupported."""
    system = platform.system()
    if system == "Windows":
        nodeos, ext = "win", "zip"
    elif system == "Linux":
        nodeos, ext = "linux", "tar.gz"
    elif system == "Darwin":
        nodeos, ext = "darwin", "tar.gz"
    else:
        return None
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        nodearch = "x64"
    elif machine in ("arm64", "aarch64"):
        nodearch = "arm64"
    else:
        return None
    return nodeos, nodearch, ext


def install_base(project_slug: str) -> Path:
    """User-local install root (matches the launch scripts' location)."""
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / project_slug
    return Path.home() / ".local" / "share" / project_slug


def _reachable(host: str, timeout: float = 3.0) -> bool:
    """True if ``https://<host>/`` answers within ``timeout`` (any HTTP response
    counts; only a connection failure/timeout means unreachable). Uses urllib so it
    honors the system/env proxy — matching the proxy-aware download below."""
    import urllib.error

    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"https://{host}/", method="HEAD"), timeout=timeout
        ):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def _extract(archive: Path, dest: Path, ext: str) -> None:
    if ext == "zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    elif sys.version_info >= (3, 12):  # trusted official/npmmirror tarball
        with tarfile.open(archive) as tf:
            tf.extractall(dest, filter="data")
    else:
        with tarfile.open(archive) as tf:
            tf.extractall(dest)


def _emit(log, msg: str) -> None:
    if log is not None:
        log.write(msg + "\n")
        log.flush()


def _sources(prefer_mirror: bool) -> list[str]:
    """Dist bases to try in order. ``HF_NODE_DIST`` overrides; otherwise mirror-first
    behind the GFW (``prefer_mirror``), official-first elsewhere — and the OTHER is
    always kept as a fallback."""
    forced = os.environ.get("HF_NODE_DIST")
    if forced:
        return [forced.rstrip("/")]
    return [_NODE_MIRROR, _NODE_OFFICIAL] if prefer_mirror else [_NODE_OFFICIAL, _NODE_MIRROR]


def _download(url: str, dest: Path, *, log=None) -> bool:
    """Stream ``url`` -> ``dest``. ``urlopen``'s socket timeout (``_READ_TIMEOUT``)
    aborts only a STALLED connection (no data for that long); a slow-but-steady
    transfer is NOT aborted — it's ridden to completion, because a slow success beats
    a fast failure. Only a stall / connection error / HTTP error returns ``False`` and
    falls back to the next source. The default opener honors HTTP(S)_PROXY env + the
    system proxy, so a configured proxy is used automatically."""
    bucket = -1
    try:
        with urllib.request.urlopen(url, timeout=_READ_TIMEOUT) as resp:  # noqa: S310 — pinned node.js dist URL
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            with dest.open("wb") as fh:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total and got * 10 // total != bucket:  # log roughly every 10%
                        bucket = got * 10 // total
                        _emit(log, f"[harnessforge]   downloading Node ... {got * 100 // total}%")
        return True
    except Exception as exc:  # stall / timeout / HTTP / connection — try the next source
        _emit(log, f"[harnessforge]   source failed: {exc}")
        dest.unlink(missing_ok=True)
        return False


def ensure_portable_node(
    project_slug: str, *, prefer_mirror: bool | None = None, log=None
) -> str | None:
    """Return a PATH directory that provides ``node``+``npx``, installing a portable
    Node if needed. Tries multiple dist sources (official + domestic mirror) in an
    order chosen by ``prefer_mirror`` (default: probe ``nodejs.org``), falling back
    when one stalls / is too slow / fails. Returns ``None`` when Node is already on
    PATH, the platform is unsupported, or every source failed (best-effort: the
    caller proceeds without it). ``log`` (a writable file) receives progress lines.
    """
    if node_on_path():
        return None
    tag = _platform_tag()
    if tag is None:
        _emit(log, f"[harnessforge] portable Node: unsupported platform {platform.platform()!r}; skipping.")
        return None
    nodeos, nodearch, ext = tag
    dirname = f"node-{NODE_LTS_VERSION}-{nodeos}-{nodearch}"
    base_dir = install_base(project_slug)
    extracted = base_dir / dirname
    bin_dir = extracted if nodeos == "win" else extracted / "bin"
    node_exe = bin_dir / ("node.exe" if nodeos == "win" else "node")
    if node_exe.exists():
        _emit(log, f"[harnessforge] portable Node already present: {bin_dir}")
        return str(bin_dir)

    if prefer_mirror is None:  # default heuristic: official slow/blocked -> mirror first
        prefer_mirror = not _reachable("nodejs.org")
    archive = f"{dirname}.{ext}"
    base_dir.mkdir(parents=True, exist_ok=True)
    tmp = base_dir / archive
    for base in _sources(prefer_mirror):
        _emit(log, f"[harnessforge] downloading Node {NODE_LTS_VERSION} ({nodeos}-{nodearch}) from {base} ...")
        if not _download(f"{base}/{NODE_LTS_VERSION}/{archive}", tmp, log=log):
            _emit(log, "[harnessforge] trying the next source ...")
            continue
        try:
            _emit(log, "[harnessforge] extracting Node ...")
            _extract(tmp, base_dir, ext)
            tmp.unlink(missing_ok=True)
        except Exception as exc:  # bad archive — non-fatal, stop here
            _emit(log, f"[harnessforge] portable Node extract failed: {exc}")
            return None
        if node_exe.exists():
            _emit(log, f"[harnessforge] Node is ready: {bin_dir}")
            return str(bin_dir)
        _emit(log, "[harnessforge] portable Node: node binary not found after extract.")
        return None
    _emit(log, "[harnessforge] portable Node: all sources failed (see proxy / network).")
    return None
