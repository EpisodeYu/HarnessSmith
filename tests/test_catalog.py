"""MCP server catalog loader tests (Slice 6; fast — no network/uv)."""

from __future__ import annotations

import pytest

from harnessmith.catalog import (
    CatalogError,
    CatalogServer,
    available_servers,
    get_server,
    load_catalog,
    resolve_servers,
)


@pytest.mark.parametrize(
    "kwargs,secret",
    [
        ({"env": ["sk-secret"]}, "sk-secret"),
        (
            {"auth_env": "ghp_abcdefghijklmnopqrstuvwxyz123456"},
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
        ),
        (
            {"env_const": {"ghp_abcdefghijklmnopqrstuvwxyz123456": "not-a-secret"}},
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
        ),
    ],
)
def test_catalog_env_references_reject_secrets_without_echo(kwargs, secret):
    with pytest.raises(CatalogError) as caught:
        CatalogServer(name="unsafe", command="x", **kwargs)
    assert secret not in str(caught.value)


def test_catalog_loads_baseline_servers():
    catalog = load_catalog()
    for name in ("fetch", "git", "desktop-commander"):
        assert name in catalog
    assert "fetch" in available_servers()


def test_web_search_is_keyless_multi_engine_node():
    """Default web search: a keyless, multi-engine, failover scraper (open-websearch,
    Node). `env_const` forces pure-stdio (MODE=stdio) so it doesn't also bind HTTP;
    the version is pinned so warm installs exactly what the connect launches."""
    web = get_server("web-search")
    assert web.command == "npx"
    assert web.requires == "node"
    assert web.args == ["-y", "open-websearch@2.1.11"]
    assert web.env_const == {"MODE": "stdio"}  # literal non-secret: pure-stdio mode
    assert web.auth_env is None and web.env == []  # keyless (no secret names)
    assert web.uvx_package is None  # npx, not uvx
    assert "search" in web.safe_tools and "fetchWebContent" in web.safe_tools
    # server_entry carries env_const into config.yaml (env names stay separate).
    entry = web.server_entry()
    assert entry["env_const"] == {"MODE": "stdio"} and "env" not in entry
    # The prefill is a single `<server>__*` wildcard enabling the whole server.
    assert web.allowlist_entries() == [{"name": "web-search__*", "enabled": True}]


def test_ddg_search_is_keyless_uvx_web_search():
    ddg = get_server("ddg-search")
    assert ddg.command == "uvx"
    assert ddg.uvx_package == "duckduckgo-mcp-server"
    assert ddg.auth_env is None and ddg.env == []  # keyless
    assert ddg.safe_tools == ["search", "fetch_content"]  # read-only -> usable by plan/ask
    # The prefill is a single `<server>__*` wildcard enabling the whole server.
    assert ddg.allowlist_entries() == [{"name": "ddg-search__*", "enabled": True}]


def test_fetch_is_a_safe_uvx_server():
    fetch = get_server("fetch")
    assert fetch.command == "uvx"
    # uvx_package skips flags, so it still resolves to the package (for warm/Docker).
    assert fetch.uvx_package == "mcp-server-fetch"
    assert fetch.safe_tools == ["fetch"]
    entry = fetch.server_entry()
    assert entry["command"] == "uvx"
    assert entry["safe_tools"] == ["fetch"]
    # --ignore-robots-txt lets user-directed reads (e.g. the keyless r.jina.ai
    # reader the web-reading skill uses) through; mcp-server-fetch otherwise honors
    # robots.txt and refuses r.jina.ai (which Disallows `*`).
    assert entry["args"] == ["mcp-server-fetch", "--ignore-robots-txt"]


def test_git_reads_are_safe_writes_are_high():
    git = get_server("git")
    assert "git_status" in git.safe_tools
    assert "git_log" in git.safe_tools
    assert "git_commit" not in git.safe_tools  # mutating -> high (but still enabled by the wildcard)
    # The wildcard enables every git tool (reads + writes); `safe_tools` keeps the
    # reads at risk=safe so plan/ask can use them, writes stay risk=high.
    assert git.allowlist_entries() == [{"name": "git__*", "enabled": True}]


def test_desktop_commander_is_node_and_wildcard_enabled():
    dc = get_server("desktop-commander")
    assert dc.command == "npx"
    assert dc.requires == "node"
    assert dc.uvx_package is None  # not baked into the image
    # `--silent` keeps npm's first-launch install summary off the child's stdout
    # (which must be pure JSON-RPC); it precedes the package so it's npm's flag. The
    # version is PINNED (not @latest) so warm-on-first-run caches exactly what the
    # later connect resolves — `@latest` could re-resolve and miss the warmed copy.
    assert dc.args == ["--silent", "-y", "@wonderwhy-er/desktop-commander@0.2.42"]
    assert dc.server_entry()["args"] == ["--silent", "-y", "@wonderwhy-er/desktop-commander@0.2.42"]
    # Read-only tools are safe (so plan/ask can read files/list dirs/search code);
    # write/shell/config-mutating tools stay high-risk (agent-only).
    assert "read_file" in dc.safe_tools
    assert "list_directory" in dc.safe_tools
    assert "start_search" in dc.safe_tools
    assert "write_file" not in dc.safe_tools  # mutating -> high
    assert "start_process" not in dc.safe_tools  # shell -> high
    assert "set_config_value" not in dc.safe_tools  # config write -> high
    # A single wildcard enables the server's whole toolset (reads + writes/shell);
    # `safe_tools` keeps the reads at risk=safe so plan/ask can use them.
    assert dc.allowlist_entries() == [{"name": "desktop-commander__*", "enabled": True}]


def test_remote_server_entry_uses_url_and_auth_env():
    gh = get_server("github")
    entry = gh.server_entry()
    assert entry["url"].startswith("https://")
    assert entry["auth_env"] == "GITHUB_MCP_TOKEN"
    assert "command" not in entry


def test_bocha_is_keyed_uvx_china_search():
    """Bocha (博查): a key-based, China-compliant search SUPPLEMENT to the keyless
    web-search. uvx-based (rides uv, no Node) so it can be prewarmed/baked offline;
    the API key is an env NAME only; both search tools are read-only -> safe."""
    bocha = get_server("bocha")
    assert bocha.command == "uvx"
    assert bocha.uvx_package == "mcp-bocha-search"  # prewarmable/bakeable
    assert bocha.requires == "uv"
    assert bocha.env == ["BOCHA_API_KEY"]  # secret NAME only (stdio env)
    assert bocha.auth_env is None  # stdio key rides `env`, not a remote Bearer
    # Both tools are read-only network reads -> safe (plan/ask can search too).
    assert bocha.safe_tools == ["bocha_web_search", "bocha_ai_search"]
    entry = bocha.server_entry()
    assert entry["command"] == "uvx" and entry["args"] == ["mcp-bocha-search"]
    assert entry["env"] == ["BOCHA_API_KEY"]  # NAME carried into config.yaml
    # The prefill is a single `<server>__*` wildcard enabling the whole server.
    assert bocha.allowlist_entries() == [{"name": "bocha__*", "enabled": True}]


def test_jina_reader_remote_renders_complex_pages():
    """Jina Reader: a remote (Streamable HTTP) MCP for reading complex/JS pages
    where the keyless fetch falls short. url + Bearer auth_env (NAME only); read
    tools are read-only -> safe (offered to plan/ask)."""
    jina = get_server("jina-reader")
    entry = jina.server_entry()
    assert entry["url"] == "https://mcp.jina.ai/v1"
    assert entry["auth_env"] == "JINA_API_KEY"  # optional Bearer, NAME only
    assert "command" not in entry  # remote, not a local subprocess
    assert jina.command is None and jina.requires is None  # no uv/node launcher
    # read_url (+ parallel/search) are read-only network reads -> safe.
    assert "read_url" in jina.safe_tools and "search_web" in jina.safe_tools
    assert jina.allowlist_entries() == [{"name": "jina-reader__*", "enabled": True}]


def test_resolve_servers_dedupes_and_validates():
    resolved = resolve_servers(["fetch", "git", "fetch"])
    assert [s.name for s in resolved] == ["fetch", "git"]
    with pytest.raises(CatalogError):
        resolve_servers(["does-not-exist"])
