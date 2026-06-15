"""Wizard tests (Slice 7): structural-only form, baked defaults, isolation.

The wizard is a generator-side tool behind the ``harnessmith[wizard]`` extra.
Its UI collects only *structural* choices (what to generate); behavioral fields
(llms/prompts/tools/context) are baked with working defaults and edited later in
the generated product. These drive it with ``fastapi.testclient`` (no real
browser). They are skipped if FastAPI isn't installed (``uv sync --extra dev``).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from harnessmith.wizard.app import create_app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(create_app())


def _valid_spec() -> dict:
    """A structural-only form payload (what the slimmed wizard UI sends)."""
    return {
        "display_name": "My Coding Assistant",
        "project_slug": "my_ca",
        "language": "zh",
        "paradigms": ["agent", "plan"],
        "interfaces": {"cli": True, "web": True},
        "mcp": {"enabled": True},
        "skills": {"enabled": False},
    }


def test_index_serves_language_first(client):
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()
    # Language is the first-class control; both languages are offered.
    assert 'id="lang"' in r.text and "中文" in r.text and "English" in r.text


def test_wizard_ui_is_structural_only(client):
    """The form exposes structural switches, not behavioral config (that lives in
    the generated product's config page)."""
    html = client.get("/").text
    for needed in ('id="display_name"', 'id="iface_web"', 'id="mcp_enabled"',
                   'id="skills_enabled"', 'id="memory_enabled"', "paradigms-list"):
        assert needed in html, needed
    for absent in ("add-profile", "b_max_steps", "ctx_strategy", "rules_files", "llm_language"):
        assert absent not in html, absent


def test_meta_lists_paradigms_and_catalog(client):
    m = client.get("/meta").json()
    assert {"agent", "plan", "ask"} <= {p["name"] for p in m["paradigms"]}
    assert "fetch" in {s["name"] for s in m["catalog"]}


def test_meta_catalog_curates_order_defaults_and_hides_niche(client):
    """The wizard surfaces a curated subset, fetch/web-search/git first and
    desktop-commander last; github (needs token) and time (niche) are hidden.
    web-search is the default web search (keyless multi-engine; ddg-search is the
    catalog-only uvx fallback). Desktop Commander is checked by default (Slice 11)
    — HITL-gated."""
    catalog = client.get("/meta").json()["catalog"]
    names = [s["name"] for s in catalog]
    assert names == ["fetch", "web-search", "git", "desktop-commander"]
    assert "github" not in names and "time" not in names
    checked = {s["name"] for s in catalog if s["default_checked"]}
    assert checked == {"fetch", "web-search", "git", "desktop-commander"}


def test_meta_exposes_generate_base_under_repo_root(client):
    base = client.get("/meta").json()["generate_base"]
    assert base.endswith("generate")  # <repo-root>/generate


def test_meta_exposes_linux_flag(client):
    # Gates the product port-forward hint in the UI (shown only on Linux hosts).
    assert isinstance(client.get("/meta").json()["linux"], bool)


def test_wizard_ui_defaults_capabilities_checked(client):
    """Web / MCP / Skills / Memory capabilities are checked by default in the form."""
    html = client.get("/").text
    for box in ('id="iface_web" type="checkbox" checked',
                'id="mcp_enabled" type="checkbox" checked',
                'id="skills_enabled" type="checkbox" checked',
                'id="memory_enabled" type="checkbox" checked'):
        assert box in html, box


def test_wizard_ui_has_two_generate_methods(client):
    """The Generate section offers one-click + CLI, plus the jump-to-product button."""
    html = client.get("/").text
    for needed in ('id="generate"', 'id="produce"', 'id="open-product"', 'id="target_dir"'):
        assert needed in html, needed
    # An "or" divider makes clear the two methods are alternatives, not sequential steps.
    assert 'data-i18n="or_divider"' in html
    # 'github'/'time' must not be hard-coded as catalog options in the page.
    assert "github" not in html.lower()


def test_spec_valid_returns_yaml_and_new_command(client):
    r = client.post("/spec", json={"spec": _valid_spec(), "mcp_servers": ["fetch"]})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "display_name: My Coding Assistant" in data["yaml"]
    assert "project_slug: my_ca" in data["yaml"]
    assert "language: zh" in data["yaml"]  # threads into the product default UI language
    assert "--mcp-server fetch" in data["new_command"]


def test_spec_command_fills_target_dir_when_provided(client):
    r = client.post(
        "/spec", json={"spec": _valid_spec(), "target_dir": "/tmp/generate/my_ca"}
    )
    cmd = r.json()["new_command"]
    assert cmd.startswith("harnessmith new /tmp/generate/my_ca --spec spec.yaml")


def test_spec_command_uses_placeholder_without_target_dir(client):
    cmd = client.post("/spec", json={"spec": _valid_spec()}).json()["new_command"]
    assert cmd.startswith("harnessmith new <target-dir> --spec spec.yaml")


def test_baked_defaults_fill_behavioral_fields(client):
    """Structural-only form -> backend bakes runnable behavioral defaults so the
    generated product is complete out of the box (edited later in the product)."""
    structural = {"project_slug": "barebones", "paradigms": ["agent"], "interfaces": {"cli": True}}
    y = client.post("/spec", json={"spec": structural}).json()["yaml"]
    # The LLM profile is scaffolded with the env-var NAMES but NO model — the
    # one-click wizard never asks which model, so it must not guess one
    # (gpt-4o-mini mis-fires on non-OpenAI providers). The product gates chat
    # until the user sets a model on its own config page.
    assert "name: default" in y                # default LLM profile (scaffold)
    assert "gpt-4o-mini" not in y              # no guessed model
    assert "api_key_env: OPENAI_API_KEY" in y  # env NAME only
    assert "You are a capable AI assistant." in y  # default system prompt (baked)
    # Cost accounting / limits are runtime-only (config.yaml's Budget page), never
    # in the spec — so the baked spec has no budget block.
    assert "budget:" not in y


def test_explicit_behavioral_fields_win_over_defaults(client):
    """A spec that already carries behavioral fields is not overwritten."""
    spec = {"project_slug": "ex", "paradigms": ["agent"],
            "llms": [{"name": "x", "model": "my-model", "api_key_env": "MY_KEY"}],
            "roles": {"generation": "x"}}
    y = client.post("/spec", json={"spec": spec}).json()["yaml"]
    assert "model: my-model" in y and "gpt-4o-mini" not in y


def test_spec_invalid_slug_returns_field_errors(client):
    r = client.post("/spec", json={"spec": {"project_slug": "1bad"}})
    assert r.status_code == 400
    data = r.json()
    assert data["ok"] is False
    assert any(e["loc"] == "project_slug" for e in data["errors"])


def test_spec_only_holds_env_names_never_secret_values(client):
    # The form only ever carries env-var NAMES; there is no secret value channel.
    r = client.post("/spec", json={"spec": _valid_spec()})
    assert "OPENAI_API_KEY" in r.text  # the NAME is present (baked default profile)...
    assert "sk-" not in r.text  # ...but no secret-looking value is ever echoed


def test_spec_unknown_catalog_server_rejected(client):
    r = client.post("/spec", json={"spec": _valid_spec(), "mcp_servers": ["does-not-exist"]})
    assert r.status_code == 400
    assert any(e["loc"] == "mcp_servers" for e in r.json()["errors"])


def test_language_threads_into_product_default(client):
    r = client.post("/spec", json={"spec": {**_valid_spec(), "language": "en"}})
    assert r.status_code == 200
    assert "language: en" in r.json()["yaml"]


def test_memory_toggle_flows_through_to_spec_and_repo(client, tmp_path):
    """The wizard's memory switch threads into the spec + generates memory.py."""
    spec = {**_valid_spec(), "memory": {"enabled": True}}
    y = client.post("/spec", json={"spec": spec}).json()["yaml"]
    assert "memory:" in y and "enabled: true" in y

    out = tmp_path / "mem"
    r = client.post("/generate", json={"spec": spec, "target_dir": str(out)})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert (out / "src" / "my_ca" / "harness" / "memory.py").is_file()

    # Off (or omitted) leaves zero memory footprint.
    out2 = tmp_path / "nomem"
    spec_off = {**_valid_spec(), "memory": {"enabled": False}}
    client.post("/generate", json={"spec": spec_off, "target_dir": str(out2)})
    assert not (out2 / "src" / "my_ca" / "harness" / "memory.py").exists()


def test_generate_renders_repo_with_display_name(client, tmp_path):
    out = tmp_path / "gen"
    r = client.post("/generate", json={"spec": _valid_spec(), "target_dir": str(out)})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert (out / "README.md").read_text(encoding="utf-8").splitlines()[0] == "# My Coding Assistant"
    assert (out / "src" / "my_ca" / "interfaces" / "web.py").is_file()


def test_generate_requires_target_dir(client):
    r = client.post("/generate", json={"spec": _valid_spec()})
    assert r.status_code == 400
    assert any(e["loc"] == "target_dir" for e in r.json()["errors"])


def test_generate_refuses_non_empty_dir(client, tmp_path):
    out = tmp_path / "gen"
    out.mkdir()
    (out / "x.txt").write_text("hi", encoding="utf-8")
    r = client.post("/generate", json={"spec": _valid_spec(), "target_dir": str(out)})
    assert r.status_code == 400 and r.json()["ok"] is False


def test_generate_launches_product_with_progress_job(client, tmp_path, monkeypatch):
    """One-click generate + ``launch`` returns a job whose step-by-step status the
    UI polls; the product URL appears only once the job is done. The worker is
    stubbed so the test never runs uv / opens a port."""
    import harnessmith.wizard.app as app_mod

    calls = {}

    def fake_spawn(job, target_dir, project_slug, *, index_url=None, serve_timeout=300.0):
        calls["project_slug"] = project_slug
        for step in job["steps"]:
            step["status"] = "done"
        job["url"] = "http://127.0.0.1:8123"
        job["done"] = True

    monkeypatch.setattr(app_mod, "_spawn_launch", fake_spawn)
    out = tmp_path / "gen"
    r = client.post(
        "/generate",
        json={"spec": _valid_spec(), "target_dir": str(out), "launch": True},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert calls["project_slug"] == "my_ca"
    status = client.get(f"/generate/status/{job_id}").json()
    assert [s["key"] for s in status["steps"]] == ["render", "sync", "serve"]
    assert status["done"] is True
    assert status["url"] == "http://127.0.0.1:8123"


def test_generate_status_unknown_job_is_404(client):
    assert client.get("/generate/status/nope").status_code == 404


def test_product_env_drops_parent_venv(monkeypatch):
    """The product's uv calls must NOT inherit the wizard's own VIRTUAL_ENV: the
    wizard runs inside HarnessSmith's venv (via ``uv run``), and on Windows the
    product's ``uv sync`` would then fight the running parent over that venv's
    locked files and never finish. A launcher-set mirror is preserved."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setenv("VIRTUAL_ENV", "/wizard/.venv")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/wizard/.venv")
    monkeypatch.setenv("UV_DEFAULT_INDEX", "https://mirror.example/simple")
    env = app_mod._product_env()
    assert "VIRTUAL_ENV" not in env
    assert "UV_PROJECT_ENVIRONMENT" not in env
    assert env["UV_DEFAULT_INDEX"] == "https://mirror.example/simple"


def test_product_env_falls_back_to_china_mirror_when_pypi_unreachable(monkeypatch):
    """No index pinned + official PyPI unreachable (e.g. GFW) -> the product's uv
    calls get the Tsinghua mirror filled in automatically."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: False)
    for k in app_mod._INDEX_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert app_mod._product_env()["UV_DEFAULT_INDEX"] == app_mod._CN_PYPI_MIRROR


def test_product_env_keeps_official_when_pypi_reachable(monkeypatch):
    """No index pinned + official PyPI reachable -> leave uv on its default index."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: True)
    for k in app_mod._INDEX_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert "UV_DEFAULT_INDEX" not in app_mod._product_env()


def test_product_env_never_overrides_an_explicit_index(monkeypatch):
    """An explicitly-pinned index (e.g. set by the launcher) is never replaced,
    even when the probe would say PyPI is unreachable."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: False)
    monkeypatch.setenv("UV_DEFAULT_INDEX", "https://my.own/simple")
    assert app_mod._product_env()["UV_DEFAULT_INDEX"] == "https://my.own/simple"


def test_pypi_reachable_classifies_responses(monkeypatch):
    """A server response (even an HTTP error status) counts as reachable; only a
    connection failure / timeout counts as unreachable."""
    import urllib.error

    import harnessmith.wizard.app as app_mod

    def http_error(*a, **k):
        raise urllib.error.HTTPError("u", 405, "no", {}, None)

    monkeypatch.setattr(app_mod.urllib.request, "urlopen", http_error)
    assert app_mod._pypi_reachable() is True

    def conn_error(*a, **k):
        raise urllib.error.URLError("blocked")

    monkeypatch.setattr(app_mod.urllib.request, "urlopen", conn_error)
    assert app_mod._pypi_reachable() is False


def test_status_streams_live_setup_log_tail(client, tmp_path):
    """While sync runs, the status endpoint tacks uv's latest output (read live
    from .setup.log) onto the job so the UI shows it progressing, not frozen."""
    import harnessmith.wizard.app as app_mod

    log = tmp_path / ".setup.log"
    log.write_text(
        "Resolved 42 packages\nDownloading openai\nPrepared 42 packages\n",
        encoding="utf-8",
    )
    job = app_mod._new_job()
    job["setup_log"] = str(log)
    app_mod._JOBS[job["id"]] = job
    try:
        data = client.get(f"/generate/status/{job['id']}").json()
    finally:
        app_mod._JOBS.pop(job["id"], None)
    assert "Prepared 42 packages" in data["log_tail"]


def test_run_launch_reports_sync_failure_without_hanging(tmp_path, monkeypatch):
    """A non-zero ``uv sync`` marks the sync step 'error' and records a message
    with the log path + tail, then the worker returns — the UI stops spinning
    instead of hanging on a stuck install."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(
        app_mod, "_uv_sync", lambda target_dir, **kw: (124, "error: failed to fetch index")
    )
    job = app_mod._new_job()
    app_mod._run_launch(job, tmp_path, "my_harness")

    sync = next(s for s in job["steps"] if s["key"] == "sync")
    assert sync["status"] == "error"
    assert job["done"] is False
    assert ".setup.log" in job["error"]
    assert "failed to fetch index" in job["error"]
    # serve must not start once sync failed
    assert next(s for s in job["steps"] if s["key"] == "serve")["status"] == "pending"


def test_run_launch_provisions_portable_node_for_node_servers(tmp_path, monkeypatch):
    """When a Node-based MCP server is prefilled, the headless launch inserts a
    'node' step, provisions a portable Node, and prepends its bin dir to the
    product's PATH (so npx works) — the one-click flow that bypasses <slug>.bat/.sh."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_uv_sync", lambda td, **kw: (0, ""))
    monkeypatch.setattr(app_mod, "node_on_path", lambda: False)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: True)  # no real network
    captured = {}

    def fake_ensure(slug, *, prefer_mirror=None, log=None):
        captured["prefer_mirror"] = prefer_mirror
        return "/portable/node/bin"

    monkeypatch.setattr(app_mod, "ensure_portable_node", fake_ensure)
    monkeypatch.setattr(app_mod, "_find_free_port", lambda: 8123)
    monkeypatch.setattr(app_mod, "_wait_port", lambda host, port, timeout=None: True)
    monkeypatch.setattr(
        app_mod, "_launch_product",
        lambda td, slug, port, *, host="127.0.0.1", extra_path=None, index_url=None: captured.update(extra_path=extra_path),
    )

    job = app_mod._new_job(needs_node=True)
    assert [s["key"] for s in job["steps"]] == ["render", "sync", "node", "serve"]
    app_mod._run_launch(job, tmp_path, "demo")

    assert job["done"] is True
    for key in ("sync", "node", "serve"):
        assert next(s for s in job["steps"] if s["key"] == key)["status"] == "done"
    assert captured["extra_path"] == "/portable/node/bin"  # node bin dir reached serve
    assert captured["prefer_mirror"] is False  # PyPI reachable -> official first


def test_run_launch_skips_node_download_when_node_present(tmp_path, monkeypatch):
    """If Node is already on PATH, the 'node' step is a no-op (no download) and the
    product launches with the unmodified PATH."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_uv_sync", lambda td, **kw: (0, ""))
    monkeypatch.setattr(app_mod, "node_on_path", lambda: True)
    monkeypatch.setattr(
        app_mod, "ensure_portable_node",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not download Node")),
    )
    monkeypatch.setattr(app_mod, "_find_free_port", lambda: 8123)
    monkeypatch.setattr(app_mod, "_wait_port", lambda host, port, timeout=None: True)
    captured = {}
    monkeypatch.setattr(
        app_mod, "_launch_product",
        lambda td, slug, port, *, host="127.0.0.1", extra_path=None, index_url=None: captured.update(extra_path=extra_path),
    )
    job = app_mod._new_job(needs_node=True)
    app_mod._run_launch(job, tmp_path, "demo")
    assert job["done"] is True
    assert next(s for s in job["steps"] if s["key"] == "node")["status"] == "done"
    assert captured["extra_path"] is None


def test_ensure_proxy_env_fills_from_system_proxy(monkeypatch):
    """_product_env fills HTTP(S)_PROXY from the system proxy when unset (so uv sync
    + the product's npx servers reach the net through a corporate proxy), but never
    overrides one the user already set."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(
        app_mod.urllib.request, "getproxies", lambda: {"https": "http://corp:8080"}
    )
    env = {}
    app_mod._ensure_proxy_env(env)
    assert env["HTTP_PROXY"] == "http://corp:8080"
    assert env["HTTPS_PROXY"] == "http://corp:8080"

    env2 = {"HTTP_PROXY": "http://mine:1"}
    app_mod._ensure_proxy_env(env2)
    assert env2["HTTP_PROXY"] == "http://mine:1"  # user's proxy is left untouched


def test_generate_does_not_launch_without_web(client, tmp_path, monkeypatch):
    """A CLI-only spec (no Web) is render-only even with ``launch`` requested."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(
        app_mod, "_spawn_launch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    spec = {**_valid_spec(), "interfaces": {"cli": True, "web": False}}
    out = tmp_path / "gen"
    r = client.post("/generate", json={"spec": spec, "target_dir": str(out), "launch": True})
    assert r.status_code == 200
    assert "job_id" not in r.json()


def test_generate_render_only_by_default(client, tmp_path, monkeypatch):
    """Without ``launch`` the generate stays render-only (no product spawned)."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(
        app_mod, "_spawn_launch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    out = tmp_path / "gen"
    r = client.post("/generate", json={"spec": _valid_spec(), "target_dir": str(out)})
    assert r.status_code == 200 and "job_id" not in r.json()


def test_core_dependencies_exclude_wizard_deps():
    """Isolation: fastapi/uvicorn live only in extras, never core `dependencies`,
    so `uvx harnessmith new` and generated products never pull them."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core = " ".join(data["project"]["dependencies"]).lower()
    assert "fastapi" not in core and "uvicorn" not in core
    extras = data["project"]["optional-dependencies"]
    assert any("fastapi" in d for d in extras["wizard"])


# The real Windows failure tail (os error 5 / 拒绝访问 while uv renames a cache entry).
_CACHE_ERR_LOG = (
    "Downloaded openai\n"
    "  × Failed to download `anthropic==0.109.1`\n"
    "  ├─▶ Failed to read from the distribution cache\n"
    "  ╰─▶ failed to rename file from C:\\...\\.tmpoEP1d7 to "
    "C:\\...\\archive-v0\\qBbrteLoxjqT4Tqj: 拒绝访问。 (os error 5)\n"
)


def test_looks_like_cache_corruption_matches_os_error_5():
    """The Windows cache-rename failure (os error 5 / 拒绝访问) is recognised, but a
    plain network/index failure is NOT (must never trigger a cache wipe)."""
    import harnessmith.wizard.app as app_mod

    assert app_mod._looks_like_cache_corruption(_CACHE_ERR_LOG) is True
    assert app_mod._looks_like_cache_corruption(
        "error: Failed to fetch https://pypi.org/simple/: connection timed out"
    ) is False
    # access-denied alone, without a cache/rename context, is not our signature
    assert app_mod._looks_like_cache_corruption("permission denied: access is denied") is False


def test_uv_sync_self_heals_corrupt_cache(tmp_path, monkeypatch):
    """On the cache-corruption signature, ``_uv_sync`` runs ``uv cache clean`` once
    and retries the sync — the retry succeeding yields exit code 0."""
    import harnessmith.wizard.app as app_mod

    calls: list[list[str]] = []

    def fake_run_uv(args, *, cwd, log, index_url=None):
        calls.append(args)
        if args == ["sync"] and calls.count(["sync"]) == 1:
            log.write(_CACHE_ERR_LOG)  # first sync fails with the cache error
            return 1
        log.write(f"ok: uv {' '.join(args)}\n")
        return 0  # cache clean + the retried sync both succeed

    monkeypatch.setattr(app_mod, "_run_uv", fake_run_uv)
    code, _ = app_mod._uv_sync(tmp_path)

    assert code == 0
    assert calls == [["sync"], ["cache", "clean"], ["sync"]]


def test_uv_sync_does_not_clean_cache_on_network_failure(tmp_path, monkeypatch):
    """A non-cache failure (e.g. unreachable index) must NOT wipe the cache: only
    the single sync runs and its non-zero code is returned as-is."""
    import harnessmith.wizard.app as app_mod

    calls: list[list[str]] = []

    def fake_run_uv(args, *, cwd, log, index_url=None):
        calls.append(args)
        log.write("error: Failed to fetch https://pypi.org/simple/: timed out\n")
        return 1

    monkeypatch.setattr(app_mod, "_run_uv", fake_run_uv)
    code, tail = app_mod._uv_sync(tmp_path)

    assert code == 1
    assert calls == [["sync"]]  # no `uv cache clean` retry
    assert "Failed to fetch" in tail


def test_resolve_index_precedence(monkeypatch):
    """Index precedence (drives both the .setup.log line and the env wiring): an
    explicit per-run choice wins; else an env-pinned index (reported as-is); else the
    auto probe — the China mirror when PyPI is unreachable, official PyPI otherwise."""
    import harnessmith.wizard.app as app_mod

    for k in app_mod._INDEX_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)

    # explicit beats even a pinned env
    monkeypatch.setenv("UV_DEFAULT_INDEX", "https://pinned/simple")
    assert app_mod._resolve_index("https://my.mirror/simple") == (
        "https://my.mirror/simple", "explicit",
    )
    # no explicit -> the pinned env index, surfaced verbatim
    assert app_mod._resolve_index() == ("https://pinned/simple", "env-pinned")

    # nothing pinned + PyPI unreachable -> the China mirror (auto)
    monkeypatch.delenv("UV_DEFAULT_INDEX", raising=False)
    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: False)
    assert app_mod._resolve_index() == (app_mod._CN_PYPI_MIRROR, "auto-mirror")

    # nothing pinned + PyPI reachable -> uv's built-in official default
    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: True)
    assert app_mod._resolve_index() == ("official PyPI", "auto-official")


def test_product_env_explicit_index_overrides_everything(monkeypatch):
    """The wizard's optional per-run index (e.g. a fast mirror reachable through a slow
    corporate proxy) overrides even an env-pinned UV_DEFAULT_INDEX, regardless of probe."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: True)
    monkeypatch.setenv("UV_DEFAULT_INDEX", "https://pinned/simple")
    env = app_mod._product_env("https://mirrors.aliyun.com/pypi/simple/")
    assert env["UV_DEFAULT_INDEX"] == "https://mirrors.aliyun.com/pypi/simple/"


def test_product_env_blank_index_keeps_auto_behavior(monkeypatch):
    """A blank/whitespace index (the empty form field) is treated as 'auto' -> exactly
    today's behavior, so users who never touch the knob see no change."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_index_probe_cached", None)
    monkeypatch.setattr(app_mod, "_pypi_reachable", lambda *a, **k: True)
    for k in app_mod._INDEX_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert "UV_DEFAULT_INDEX" not in app_mod._product_env("   ")


def test_uv_sync_logs_the_chosen_index(tmp_path, monkeypatch):
    """The first .setup.log line records which index the install actually used, so a
    slow/failed sync is diagnosable after the fact (which source? auto or explicit?)."""
    import harnessmith.wizard.app as app_mod

    monkeypatch.setattr(app_mod, "_run_uv", lambda args, *, cwd, log, index_url=None: 0)
    app_mod._uv_sync(tmp_path, index_url="https://mirrors.aliyun.com/pypi/simple/")
    first = (tmp_path / ".setup.log").read_text(encoding="utf-8").splitlines()[0]
    assert first == (
        "[harnessmith] package index: https://mirrors.aliyun.com/pypi/simple/ (explicit)"
    )


def test_generate_threads_index_url_to_launch(client, tmp_path, monkeypatch):
    """A Web one-click launch passes the form's optional package index through to the
    launch worker (so a user behind a slow proxy can pin a fast mirror for this run)."""
    import harnessmith.wizard.app as app_mod

    captured: dict = {}
    monkeypatch.setattr(
        app_mod, "_spawn_launch",
        lambda job, td, slug, *, index_url=None, serve_timeout=300.0: captured.update(
            index_url=index_url, serve_timeout=serve_timeout
        ),
    )
    out = tmp_path / "gen"
    r = client.post(
        "/generate",
        json={
            "spec": _valid_spec(),
            "target_dir": str(out),
            "launch": True,
            "index_url": "https://mirrors.aliyun.com/pypi/simple/",
        },
    )
    assert r.status_code == 200 and "job_id" in r.json()
    assert captured["index_url"] == "https://mirrors.aliyun.com/pypi/simple/"


def test_generate_scales_serve_timeout_to_mcp_server_count(client, tmp_path, monkeypatch):
    """First-run ``serve`` foreground-warms each stdio MCP package before binding, so
    the one-click launch scales the web-reachability wait to the prefilled stdio-server
    count (not the 300s base) — a slow cold warm isn't misreported as a dead web."""
    import harnessmith.wizard.app as app_mod

    captured: dict = {}
    monkeypatch.setattr(
        app_mod, "_spawn_launch",
        lambda job, td, slug, *, index_url=None, serve_timeout=300.0: captured.update(
            serve_timeout=serve_timeout
        ),
    )
    out = tmp_path / "gen"
    r = client.post(
        "/generate",
        json={
            "spec": _valid_spec(),
            "target_dir": str(out),
            "launch": True,
            "mcp_servers": ["fetch", "git", "web-search"],  # 3 stdio servers to warm
        },
    )
    assert r.status_code == 200 and "job_id" in r.json()
    assert captured["serve_timeout"] == 450.0  # max(300, 150 * 3 stdio servers)


def test_wizard_ui_exposes_optional_package_index(client):
    """The one-click form surfaces the optional package-index knob (blank = auto), so a
    user behind a slow proxy can pick a faster mirror without editing env vars."""
    html = client.get("/").text
    assert 'id="index_url"' in html and 'id="index_suggestions"' in html
    assert "mirrors.aliyun.com/pypi/simple" in html  # a suggested fast-via-proxy mirror


def test_root_launchers_set_system_proxy_before_probing_pypi():
    """The repo-root launchers populate HTTP(S)_PROXY from the system proxy BEFORE the
    curl PyPI probe, so curl (which ignores the WinINET/macOS GUI proxy on its own)
    sees the network the same way uv/urllib do. Otherwise the probe could wrongly
    report PyPI unreachable behind a corporate proxy and pin a mirror the proxy can't
    even reach (the very regression that motivated this)."""
    bat = (REPO_ROOT / "HarnessSmith.bat").read_text(encoding="utf-8")
    sh = (REPO_ROOT / "HarnessSmith.sh").read_text(encoding="utf-8")

    # Windows: read the WinINET registry proxy before the curl probe at :run.
    assert "Internet Settings" in bat
    assert bat.index("Internet Settings") < bat.index("pypi.org/simple/")

    # POSIX: macOS GUI proxy via scutil, applied (pick_proxy call) before pick_index.
    assert "scutil --proxy" in sh
    assert sh.index("\npick_proxy\n") < sh.index("\n  pick_index\n")
