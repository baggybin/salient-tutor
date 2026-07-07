"""LM Studio model management routes — list (with loaded-state), load, unload.

These hit LM Studio's NATIVE REST API (/api/v0/models, /api/v1/models/{load,unload})
— distinct from the OpenAI-compatible /v1/* endpoints. All three are FAIL-SAFE:
a down/unreachable server returns {reachable:false} or {ok:false} (never a 500),
and a failed load surfaces LM Studio's error message + the currently-loaded list
so the operator can see what to unload for a 'no room' failure. No VRAM-quantity
endpoint is exposed, so 'is there room' is answered by attempting the load and
reporting the outcome rather than pre-checking free memory.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from salient_tutor import web


class _DaemonShell:
    """Bare daemon with the embed profile populated so _lms_resolve finds a
    base_url (the routes fall back to the embed config)."""

    def __init__(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        self.profile = {"embeddings": {"base_url": "http://ai.home:1234", "model": "x"}}


def _client(tmp_path, monkeypatch):
    shell = _DaemonShell(tmp_path, monkeypatch)
    monkeypatch.setattr(web, "daemon", shell)
    return TestClient(web.app)


class TestLmsModelsFailSafe:
    def test_unreachable_returns_reachable_false(self, tmp_path, monkeypatch):
        r = _client(tmp_path, monkeypatch).get(
            "/api/lms/models", params={"base_url": "http://127.0.0.1:1"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["reachable"] is False
        assert body["models"] == [] and body["loaded"] == []

    def test_no_base_url_and_no_config(self, tmp_path, monkeypatch):
        # Daemon with no embed profile → _lms_resolve returns None.
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))

        class _Empty:
            profile = {}

        monkeypatch.setattr(web, "daemon", _Empty())
        r = TestClient(web.app).get("/api/lms/models")
        assert r.status_code == 200
        assert r.json()["reachable"] is False

    def test_uses_saved_base_url_when_param_omitted(self, tmp_path, monkeypatch):
        # No base_url param → falls back to the embed config's base_url. Use an
        # unreachable saved URL so the fallback is proven (the error mentions it)
        # without depending on a live server being up.
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))

        class _Saved:
            profile = {"embeddings": {"base_url": "http://127.0.0.1:1", "model": "x"}}

        monkeypatch.setattr(web, "daemon", _Saved())
        r = TestClient(web.app).get("/api/lms/models")
        assert r.status_code == 200
        assert r.json()["reachable"] is False


class TestLmsLoadFailSafe:
    def test_unreachable_returns_ok_false_fast(self, tmp_path, monkeypatch):
        # Connection-refused is instant even though the load timeout is 180s —
        # the timeout only governs a connected-but-slow server.
        r = _client(tmp_path, monkeypatch).post(
            "/api/lms/load", json={"base_url": "http://127.0.0.1:1", "model": "m"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["model"] == "m"
        assert "error" in body and body["loaded"] == []

    def test_missing_model(self, tmp_path, monkeypatch):
        r = _client(tmp_path, monkeypatch).post(
            "/api/lms/load", json={"base_url": "http://127.0.0.1:1"}
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestLmsUnloadFailSafe:
    def test_unreachable_returns_ok_false(self, tmp_path, monkeypatch):
        r = _client(tmp_path, monkeypatch).post(
            "/api/lms/unload", json={"base_url": "http://127.0.0.1:1", "model": "m"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["model"] == "m"

    def test_missing_model(self, tmp_path, monkeypatch):
        r = _client(tmp_path, monkeypatch).post(
            "/api/lms/unload", json={"base_url": "http://127.0.0.1:1"}
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False
