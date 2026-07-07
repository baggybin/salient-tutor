"""POST /api/second_opinion — endpoint passthrough + guards.

Sets the module-level daemon to a stub (no lifespan / no API key) and drives
the route with FastAPI's TestClient. Not using the client as a context manager
keeps the startup lifespan (which would build a real daemon) from firing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from salient_tutor import web


class _StubDaemon:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def second_opinion(self, question, *, timeout=180.0):
        self.calls.append(question)
        return self._payload


def test_passthrough(monkeypatch):
    payload = {
        "ok": True,
        "panel": ["tutor", "tutor_alt"],
        "agreement_score": 0.5,
        "per_agent": [],
        "judge": None,
    }
    stub = _StubDaemon(payload)
    monkeypatch.setattr(web, "daemon", stub)
    client = TestClient(web.app)
    resp = client.post("/api/second_opinion", json={"question": "teach me x"})
    assert resp.status_code == 200
    assert resp.json() == payload
    assert stub.calls == ["teach me x"]


def test_empty_question_rejected(monkeypatch):
    stub = _StubDaemon({"ok": True})
    monkeypatch.setattr(web, "daemon", stub)
    client = TestClient(web.app)
    resp = client.post("/api/second_opinion", json={"question": "   "})
    assert resp.json() == {"ok": False, "error": "no question"}
    assert stub.calls == []  # never dispatched


def test_daemon_not_started(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)
    client = TestClient(web.app)
    resp = client.post("/api/second_opinion", json={"question": "q"})
    assert resp.json() == {"ok": False, "error": "daemon not started"}
