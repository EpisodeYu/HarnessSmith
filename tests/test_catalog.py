"""MCP server catalog loader tests (Slice 6; fast — no network/uv)."""

from __future__ import annotations

import pytest

from harnessforge.catalog import (
    CatalogError,
    available_servers,
    get_server,
    load_catalog,
    resolve_servers,
)


def test_catalog_loads_baseline_servers():
    catalog = load_catalog()
    for name in ("fetch", "git", "desktop-commander"):
        assert name in catalog
    assert "fetch" in available_servers()


def test_ddg_search_is_keyless_uvx_web_search():
    ddg = get_server("ddg-search")
    assert ddg.command == "uvx"
    assert ddg.uvx_package == "duckduckgo-mcp-server"
    assert ddg.auth_env is None and ddg.env == []  # keyless
    assert ddg.safe_tools == ["search", "fetch_content"]  # read-only -> usable by plan/ask
    allow = {e["name"]: e["enabled"] for e in ddg.allowlist_entries()}
    assert allow["ddg-search__search"] is True


def test_fetch_is_a_safe_uvx_server():
    fetch = get_server("fetch")
    assert fetch.command == "uvx"
    assert fetch.uvx_package == "mcp-server-fetch"
    assert fetch.safe_tools == ["fetch"]
    entry = fetch.server_entry()
    assert entry["command"] == "uvx"
    assert entry["safe_tools"] == ["fetch"]
    assert entry["args"] == ["mcp-server-fetch"]


def test_git_reads_are_safe_writes_are_high():
    git = get_server("git")
    assert "git_status" in git.safe_tools
    assert "git_log" in git.safe_tools
    assert "git_commit" not in git.safe_tools  # mutating -> high
    allow = {e["name"]: e["enabled"] for e in git.allowlist_entries()}
    assert allow["git__git_status"] is True
    assert allow["git__git_commit"] is False


def test_desktop_commander_is_node_and_all_off():
    dc = get_server("desktop-commander")
    assert dc.command == "npx"
    assert dc.requires == "node"
    assert dc.uvx_package is None  # not baked into the image
    assert dc.safe_tools == []  # every tool high-risk
    assert all(e["enabled"] is False for e in dc.allowlist_entries())


def test_remote_server_entry_uses_url_and_auth_env():
    gh = get_server("github")
    entry = gh.server_entry()
    assert entry["url"].startswith("https://")
    assert entry["auth_env"] == "GITHUB_MCP_TOKEN"
    assert "command" not in entry


def test_resolve_servers_dedupes_and_validates():
    resolved = resolve_servers(["fetch", "git", "fetch"])
    assert [s.name for s in resolved] == ["fetch", "git"]
    with pytest.raises(CatalogError):
        resolve_servers(["does-not-exist"])
