"""Unit tests for the portable-Node helper used by the wizard's headless launch."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from harnessforge import node_bootstrap as nb


def _node_targz(dirname: str) -> bytes:
    """A minimal ``node-<ver>-<os>-<arch>/bin/node`` tarball (the official layout)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"#!/bin/sh\necho fake-node\n"
        info = tarfile.TarInfo(f"{dirname}/bin/node")
        info.size, info.mode = len(data), 0o755
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _FakeResp:
    """A urlopen-like response over in-memory bytes (context manager + read)."""

    def __init__(self, data: bytes):
        self._io = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n: int = -1) -> bytes:
        return self._io.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_node_on_path_requires_both_node_and_npx(monkeypatch):
    monkeypatch.setattr(nb.shutil, "which", lambda c: "/usr/bin/" + c)
    assert nb.node_on_path() is True
    monkeypatch.setattr(nb.shutil, "which", lambda c: None if c == "npx" else "/usr/bin/node")
    assert nb.node_on_path() is False


def test_platform_tag_maps_os_and_arch(monkeypatch):
    monkeypatch.setattr(nb.platform, "system", lambda: "Linux")
    monkeypatch.setattr(nb.platform, "machine", lambda: "x86_64")
    assert nb._platform_tag() == ("linux", "x64", "tar.gz")
    monkeypatch.setattr(nb.platform, "system", lambda: "Windows")
    monkeypatch.setattr(nb.platform, "machine", lambda: "AMD64")
    assert nb._platform_tag() == ("win", "x64", "zip")
    monkeypatch.setattr(nb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(nb.platform, "machine", lambda: "arm64")
    assert nb._platform_tag() == ("darwin", "arm64", "tar.gz")
    monkeypatch.setattr(nb.platform, "system", lambda: "Plan9")  # unsupported
    assert nb._platform_tag() is None


def test_ensure_skips_when_node_already_on_path(monkeypatch):
    monkeypatch.setattr(nb.shutil, "which", lambda c: "/usr/bin/" + c)
    assert nb.ensure_portable_node("demo") is None  # no download attempted


def _prep_linux(monkeypatch, tmp_path):
    """Mock a Linux x64 build into a tmp install root, with node NOT on PATH."""
    monkeypatch.setattr(nb, "install_base", lambda slug: tmp_path / slug)
    monkeypatch.setattr(nb.shutil, "which", lambda c: None)
    monkeypatch.setattr(nb, "_platform_tag", lambda: ("linux", "x64", "tar.gz"))
    monkeypatch.delenv("HF_NODE_DIST", raising=False)
    return f"node-{nb.NODE_LTS_VERSION}-linux-x64"


def test_ensure_downloads_extracts_and_returns_bin_dir(tmp_path, monkeypatch):
    """A successful provision extracts the official layout and returns the bin dir
    that holds node/npx — the path the caller prepends to PATH."""
    dirname = _prep_linux(monkeypatch, tmp_path)
    monkeypatch.setattr(nb, "_reachable", lambda *a, **k: True)  # official first
    tar = _node_targz(dirname)
    monkeypatch.setattr(
        nb.urllib.request, "urlopen",
        lambda url, timeout=None: _FakeResp(tar) if url.startswith(nb._NODE_OFFICIAL) else _FakeResp(b""),
    )

    bin_dir = nb.ensure_portable_node("demo")
    assert bin_dir is not None
    assert Path(bin_dir).parts[-2:] == (dirname, "bin")  # separator-agnostic
    assert (Path(bin_dir) / "node").exists()
    # Second call is a no-op reuse (already extracted) -> same dir, no re-download.
    monkeypatch.setattr(
        nb.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not re-download")),
    )
    assert nb.ensure_portable_node("demo") == bin_dir


def test_ensure_falls_back_to_next_source_when_first_fails(tmp_path, monkeypatch):
    """A source that errors/stalls is abandoned and the next is tried — so a
    throttled nodejs.org doesn't hang the step; npmmirror still completes it."""
    dirname = _prep_linux(monkeypatch, tmp_path)
    tar = _node_targz(dirname)
    seen = []

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        if url.startswith(nb._NODE_OFFICIAL):
            raise OSError("blocked/throttled")
        return _FakeResp(tar)

    monkeypatch.setattr(nb.urllib.request, "urlopen", fake_urlopen)
    bin_dir = nb.ensure_portable_node("demo", prefer_mirror=False)  # official first, then mirror
    assert bin_dir is not None and (Path(bin_dir) / "node").exists()
    assert seen[0].startswith(nb._NODE_OFFICIAL) and seen[-1].startswith(nb._NODE_MIRROR)


def test_ensure_prefer_mirror_tries_mirror_first(tmp_path, monkeypatch):
    """Behind the GFW the caller passes ``prefer_mirror=True`` so npmmirror is hit
    first (no wasted stall on official)."""
    dirname = _prep_linux(monkeypatch, tmp_path)
    tar = _node_targz(dirname)
    seen = []

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        return _FakeResp(tar)

    monkeypatch.setattr(nb.urllib.request, "urlopen", fake_urlopen)
    assert nb.ensure_portable_node("demo", prefer_mirror=True) is not None
    assert seen[0].startswith(nb._NODE_MIRROR)


def test_ensure_returns_none_when_all_sources_fail(tmp_path, monkeypatch):
    dirname = _prep_linux(monkeypatch, tmp_path)
    seen = []

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        raise OSError("blocked")

    monkeypatch.setattr(nb.urllib.request, "urlopen", fake_urlopen)
    assert nb.ensure_portable_node("demo", prefer_mirror=False) is None  # non-fatal
    assert len(seen) == 2  # both official and mirror were attempted


def test_hf_node_dist_env_forces_single_source(monkeypatch):
    monkeypatch.setenv("HF_NODE_DIST", "https://my.node/dist/")
    assert nb._sources(prefer_mirror=True) == ["https://my.node/dist"]
    assert nb._sources(prefer_mirror=False) == ["https://my.node/dist"]
