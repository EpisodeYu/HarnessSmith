"""Unit tests for the portable-Node helper used by the wizard's headless launch."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from harnessforge import node_bootstrap as nb


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


def test_ensure_downloads_extracts_and_returns_bin_dir(tmp_path, monkeypatch):
    """A successful provision extracts the official layout and returns the bin dir
    that holds node/npx — the path the caller prepends to PATH."""
    # Pin the install root so the test is host-independent: install_base keys off
    # the real sys.platform (LOCALAPPDATA on Windows, ~/.local/share on POSIX), but
    # we mock a linux build via _platform_tag, so force a matching tmp base.
    monkeypatch.setattr(nb, "install_base", lambda slug: tmp_path / slug)
    monkeypatch.setattr(nb.shutil, "which", lambda c: None)  # node NOT on PATH
    monkeypatch.setattr(nb, "_platform_tag", lambda: ("linux", "x64", "tar.gz"))
    monkeypatch.setattr(nb, "_reachable", lambda *a, **k: True)  # use official URL
    dirname = f"node-{nb.NODE_LTS_VERSION}-linux-x64"

    def fake_urlretrieve(url, dest, hook=None):
        assert dirname in url and url.startswith(nb._NODE_OFFICIAL)
        with tarfile.open(dest, "w:gz") as tf:  # minimal node-<ver>-linux-x64/bin/node
            data = b"#!/bin/sh\necho fake-node\n"
            info = tarfile.TarInfo(f"{dirname}/bin/node")
            info.size, info.mode = len(data), 0o755
            tf.addfile(info, io.BytesIO(data))
        if hook:
            hook(1, 1, 1)

    monkeypatch.setattr(nb.urllib.request, "urlretrieve", fake_urlretrieve)

    bin_dir = nb.ensure_portable_node("demo")
    assert bin_dir is not None
    assert Path(bin_dir).parts[-2:] == (dirname, "bin")  # separator-agnostic
    assert (Path(bin_dir) / "node").exists()
    # Second call is a no-op reuse (already extracted) -> same dir, no re-download.
    monkeypatch.setattr(
        nb.urllib.request, "urlretrieve",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not re-download")),
    )
    assert nb.ensure_portable_node("demo") == bin_dir


def test_ensure_uses_mirror_when_official_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(nb, "install_base", lambda slug: tmp_path / slug)
    monkeypatch.setattr(nb.shutil, "which", lambda c: None)
    monkeypatch.setattr(nb, "_platform_tag", lambda: ("linux", "x64", "tar.gz"))
    monkeypatch.setattr(nb, "_reachable", lambda *a, **k: False)  # GFW: official down
    seen = {}

    def fake_urlretrieve(url, dest, hook=None):
        seen["url"] = url
        raise OSError("blocked")  # don't actually need to extract here

    monkeypatch.setattr(nb.urllib.request, "urlretrieve", fake_urlretrieve)
    assert nb.ensure_portable_node("demo") is None  # failure is non-fatal
    assert seen["url"].startswith(nb._NODE_MIRROR)
