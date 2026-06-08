"""Wizard tests (Slice 7): structural-only form, baked defaults, isolation.

The wizard is a generator-side tool behind the ``harnessforge[wizard]`` extra.
Its UI collects only *structural* choices (what to generate); behavioral fields
(llms/prompts/budget/context) are baked with working defaults and edited later in
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

from harnessforge.wizard.app import create_app  # noqa: E402


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
    """The wizard surfaces a curated subset: default-on (fetch/ddg/git) first,
    desktop-commander last; github (needs token) and time (niche) are hidden."""
    catalog = client.get("/meta").json()["catalog"]
    names = [s["name"] for s in catalog]
    assert names == ["fetch", "ddg-search", "git", "desktop-commander"]
    assert "github" not in names and "time" not in names
    checked = {s["name"] for s in catalog if s["default_checked"]}
    assert checked == {"fetch", "ddg-search", "git"}


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
    assert cmd.startswith("harnessforge new /tmp/generate/my_ca --spec spec.yaml")


def test_spec_command_uses_placeholder_without_target_dir(client):
    cmd = client.post("/spec", json={"spec": _valid_spec()}).json()["new_command"]
    assert cmd.startswith("harnessforge new <target-dir> --spec spec.yaml")


def test_baked_defaults_fill_behavioral_fields(client):
    """Structural-only form -> backend bakes runnable behavioral defaults so the
    generated product is complete out of the box (edited later in the product)."""
    structural = {"project_slug": "barebones", "paradigms": ["agent"], "interfaces": {"cli": True}}
    y = client.post("/spec", json={"spec": structural}).json()["yaml"]
    assert "model: gpt-4o-mini" in y           # default LLM profile
    assert "api_key_env: OPENAI_API_KEY" in y  # env NAME only
    assert "You are a helpful assistant." in y  # default system prompt
    # default budget guardrail (new shape: combine + named conditions)
    assert "combine: or" in y and "max_steps:" in y and "threshold: 8" in y


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
    import harnessforge.wizard.app as app_mod

    calls = {}

    def fake_spawn(job, target_dir, project_slug):
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


def test_generate_does_not_launch_without_web(client, tmp_path, monkeypatch):
    """A CLI-only spec (no Web) is render-only even with ``launch`` requested."""
    import harnessforge.wizard.app as app_mod

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
    import harnessforge.wizard.app as app_mod

    monkeypatch.setattr(
        app_mod, "_spawn_launch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    out = tmp_path / "gen"
    r = client.post("/generate", json={"spec": _valid_spec(), "target_dir": str(out)})
    assert r.status_code == 200 and "job_id" not in r.json()


def test_core_dependencies_exclude_wizard_deps():
    """Isolation: fastapi/uvicorn live only in extras, never core `dependencies`,
    so `uvx harnessforge new` and generated products never pull them."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core = " ".join(data["project"]["dependencies"]).lower()
    assert "fastapi" not in core and "uvicorn" not in core
    extras = data["project"]["optional-dependencies"]
    assert any("fastapi" in d for d in extras["wizard"])
