"""Wizard tests (Slice 7): spec production, generation, isolation, display_name.

The wizard is a generator-side tool behind the ``harnessforge[wizard]`` extra.
These drive it with ``fastapi.testclient`` (no real browser / server). They are
skipped if FastAPI isn't installed; ``uv sync --extra dev`` provides it.
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
    return {
        "display_name": "My Coding Assistant",
        "project_slug": "my_ca",
        "paradigms": ["agent", "plan"],
        "llms": [{"name": "default", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"}],
        "roles": {"generation": "default"},
        "prompts": {"system": "You are helpful."},
        "tools": [{"name": "calculator", "enabled": True}],
        "mcp": {"enabled": True},
        "skills": {"enabled": False},
        "context": {"strategy": "truncate", "keep_last_turns": 6},
        "interfaces": {"cli": True, "web": True},
        "observability": {"trace": True, "trace_dir": "traces"},
        "budget": {"max_steps": 8},
    }


def test_index_serves_language_first(client):
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()
    # Language is the first-class control; both languages are offered.
    assert 'id="lang"' in r.text and "中文" in r.text and "English" in r.text


def test_meta_lists_paradigms_tools_and_catalog(client):
    m = client.get("/meta").json()
    assert {"agent", "plan", "ask"} <= {p["name"] for p in m["paradigms"]}
    assert {"get_current_time", "calculator"} <= {t["name"] for t in m["builtin_tools"]}
    assert "fetch" in {s["name"] for s in m["catalog"]}


def test_spec_valid_returns_yaml_and_new_command(client):
    r = client.post("/spec", json={"spec": _valid_spec(), "mcp_servers": ["fetch"]})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "display_name: My Coding Assistant" in data["yaml"]
    assert "project_slug: my_ca" in data["yaml"]
    assert "--mcp-server fetch" in data["new_command"]


def test_spec_invalid_slug_returns_field_errors(client):
    r = client.post("/spec", json={"spec": {"project_slug": "1bad"}})
    assert r.status_code == 400
    data = r.json()
    assert data["ok"] is False
    assert any(e["loc"] == "project_slug" for e in data["errors"])


def test_spec_only_holds_env_names_never_secret_values(client):
    # The form only ever carries env-var NAMES; there is no secret value channel.
    r = client.post("/spec", json={"spec": _valid_spec()})
    assert "OPENAI_API_KEY" in r.text  # the NAME is present...
    assert "sk-" not in r.text  # ...but no secret-looking value is ever echoed


def test_spec_unknown_catalog_server_rejected(client):
    r = client.post("/spec", json={"spec": _valid_spec(), "mcp_servers": ["does-not-exist"]})
    assert r.status_code == 400
    assert any(e["loc"] == "mcp_servers" for e in r.json()["errors"])


def test_language_threads_into_product_default(client):
    r = client.post("/spec", json={"spec": {**_valid_spec(), "language": "zh"}})
    assert r.status_code == 200
    assert "language: zh" in r.json()["yaml"]


def test_llm_language_directive_added_only_when_opted_in(client):
    spec = {**_valid_spec(), "language": "zh", "prompts": {"system": "You are helpful."}}
    # opted out (default): no language directive in the system prompt
    off = client.post("/spec", json={"spec": spec}).json()["yaml"]
    assert "默认用中文回答" not in off
    # opted in: a soft directive is appended, original system prompt preserved
    on = client.post("/spec", json={"spec": spec, "llm_language": True}).json()["yaml"]
    assert "You are helpful." in on and "默认用中文回答" in on


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


def test_core_dependencies_exclude_wizard_deps():
    """Isolation: fastapi/uvicorn live only in extras, never core `dependencies`,
    so `uvx harnessforge new` and generated products never pull them."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core = " ".join(data["project"]["dependencies"]).lower()
    assert "fastapi" not in core and "uvicorn" not in core
    extras = data["project"]["optional-dependencies"]
    assert any("fastapi" in d for d in extras["wizard"])
