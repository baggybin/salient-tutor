"""GET /api/config — judge/pedagogy-filter feature flag for the client.

Sets the module-level daemon to a stub (no lifespan / no API key) and drives the
route with FastAPI's TestClient without the context manager, so the startup
lifespan (which would build a real daemon) never fires.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from salient_tutor import web


class _StubDaemon:
    def __init__(self, judge: bool):
        self._judge = judge

    def judge_enabled(self) -> bool:
        return self._judge


def test_config_judge_on(monkeypatch):
    monkeypatch.setattr(web, "daemon", _StubDaemon(True))
    resp = TestClient(web.app).get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["judge"] is True
    assert body["strictness_default"] == "socratic"
    # Diagram engines are advertised so the client can gray out unavailable ones.
    assert body["diagram_engines"]["mermaid"] is True


def test_config_judge_off(monkeypatch):
    monkeypatch.setattr(web, "daemon", _StubDaemon(False))
    assert TestClient(web.app).get("/api/config").json()["judge"] is False


def test_config_daemon_not_started(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)
    body = TestClient(web.app).get("/api/config").json()
    assert body["judge"] is False
    assert body["strictness_default"] == "socratic"
    assert body["diagram_engines"]["mermaid"] is True
