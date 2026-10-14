import shutil

from app.llm.fake import FakeLLMClient
from tests.conftest import ORIGIN


def test_health_requires_token(make_client):
    c = make_client()
    assert c.get("/api/v1/health").json()["status"] == "ok"
    r = c.get("/api/v1/health", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_missing_token_rejected(make_client):
    c = make_client()
    r = c.get("/api/v1/health", headers={"Authorization": ""})
    assert r.status_code == 401


def test_origin_mismatch_rejected(client):
    assert (
        client.get("/api/v1/health", headers={"Origin": "http://evil.example"}).status_code == 403
    )
    assert client.get("/api/v1/health", headers={"Origin": ORIGIN}).status_code == 200


def test_unknown_api_path_uses_error_shape(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert "message" in r.json()["error"]


def test_settings_defaults_and_update(client):
    s = client.get("/api/v1/settings").json()
    assert s["chat_model"] == ""
    assert s["setup_completed"] is False
    r = client.put("/api/v1/settings", json={"chat_model": "m1", "setup_completed": True})
    assert r.status_code == 200
    s = client.get("/api/v1/settings").json()
    assert s["chat_model"] == "m1" and s["setup_completed"] is True


def test_settings_reject_unknown_key(client):
    r = client.put("/api/v1/settings", json={"bogus": 1})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_llm_base_url_env_override(make_client):
    c = make_client(llm_override="http://example.test/v1")
    assert c.get("/api/v1/settings").json()["llm_base_url"] == "http://example.test/v1"


def test_test_connection(make_client):
    ok = make_client(FakeLLMClient(models=["a"])).post("/api/v1/settings/test-connection").json()
    assert ok["ok"] is True and ok["models"] == ["a"]
    bad = (
        make_client(FakeLLMClient(unreachable=True)).post("/api/v1/settings/test-connection").json()
    )
    assert bad["ok"] is False and bad["message"]


def _by_id(resp):
    return {c["id"]: c for c in resp.json()["checks"]}


def test_setup_checks_all_present(make_client, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: f"/usr/bin/{exe}")
    c = make_client(FakeLLMClient(models=["chat-x:latest", "emb-y"]))
    c.put("/api/v1/settings", json={"chat_model": "chat-x", "embedding_model": "emb-y"})
    checks = _by_id(c.get("/api/v1/setup/checks"))
    assert all(ch["ok"] for ch in checks.values()), checks


def test_setup_checks_failures_and_fixes(make_client, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: None)
    c = make_client(FakeLLMClient(models=["other"]))
    c.put("/api/v1/settings", json={"chat_model": "missing-model"})
    checks = _by_id(c.get("/api/v1/setup/checks"))
    assert checks["llm_server"]["ok"]
    assert checks["chat_model"]["fix"] == "Run: ollama pull missing-model"
    assert not checks["embedding_model"]["ok"]  # not configured
    assert not checks["tesseract"]["ok"] and not checks["ffmpeg"]["ok"]


def test_setup_checks_server_unreachable(make_client, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: "/x")
    c = make_client(FakeLLMClient(unreachable=True))
    checks = _by_id(c.get("/api/v1/setup/checks"))
    assert not checks["llm_server"]["ok"]
    assert not checks["chat_model"]["ok"]
