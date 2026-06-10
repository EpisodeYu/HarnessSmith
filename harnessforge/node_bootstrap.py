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
import socket
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

NODE_LTS_VERSION = "v22.11.0"
_NODE_OFFICIAL = "https://nodejs.org/dist"
_NODE_MIRROR = "https://npmmirror.com/mirrors/node"  # domestic fallback (GFW)


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


def _reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
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


def ensure_portable_node(project_slug: str, *, log=None) -> str | None:
    """Return a PATH directory that provides ``node``+``npx``, installing a portable
    Node if needed. Returns ``None`` when Node is already on PATH, or the platform
    is unsupported, or the download failed (best-effort: the caller proceeds without
    it). ``log`` (a writable file object) receives progress lines.
    """

    def _say(msg: str) -> None:
        if log is not None:
            log.write(msg + "\n")
            log.flush()

    if node_on_path():
        return None
    tag = _platform_tag()
    if tag is None:
        _say(f"[harnessforge] portable Node: unsupported platform {platform.platform()!r}; skipping.")
        return None
    nodeos, nodearch, ext = tag
    dirname = f"node-{NODE_LTS_VERSION}-{nodeos}-{nodearch}"
    base_dir = install_base(project_slug)
    extracted = base_dir / dirname
    bin_dir = extracted if nodeos == "win" else extracted / "bin"
    node_exe = bin_dir / ("node.exe" if nodeos == "win" else "node")
    if node_exe.exists():
        _say(f"[harnessforge] portable Node already present: {bin_dir}")
        return str(bin_dir)

    base = _NODE_OFFICIAL if _reachable("nodejs.org") else _NODE_MIRROR
    archive = f"{dirname}.{ext}"
    url = f"{base}/{NODE_LTS_VERSION}/{archive}"
    base_dir.mkdir(parents=True, exist_ok=True)
    tmp = base_dir / archive
    _say(f"[harnessforge] downloading Node {NODE_LTS_VERSION} ({nodeos}-{nodearch}) from {base} ...")

    bucket = [-1]

    def _hook(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            pct = min(100, blocks * block_size * 100 // total)
            if pct // 10 != bucket[0]:  # log roughly every 10%
                bucket[0] = pct // 10
                _say(f"[harnessforge]   downloading Node ... {pct}%")

    try:
        urllib.request.urlretrieve(url, tmp, _hook)  # noqa: S310 — pinned node.js dist URL
        _say("[harnessforge] extracting Node ...")
        _extract(tmp, base_dir, ext)
        tmp.unlink(missing_ok=True)
    except Exception as exc:  # offline / mirror down / bad archive — non-fatal
        _say(f"[harnessforge] portable Node setup failed: {exc}")
        return None
    if node_exe.exists():
        _say(f"[harnessforge] Node is ready: {bin_dir}")
        return str(bin_dir)
    _say("[harnessforge] portable Node: node binary not found after extract.")
    return None
