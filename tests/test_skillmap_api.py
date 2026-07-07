"""GET /api/skillmap/graph + POST /api/skillmap/graph/rebuild — passthrough."""

from __future__ import annotations

from fastapi.testclient import TestClient

from salient_tutor import web


class _StubDaemon:
    def __init__(self):
        self.calls = []

    async def skill_graph(self, *, rebuild=False):
        self.calls.append(rebuild)
        return {
            "nodes": [{"id": "a", "label": "a", "status": "mastered"}],
            "edges": [],
            "counts": {"mastered": 1},
        }


def test_graph_passthrough(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    resp = TestClient(web.app).get("/api/skillmap/graph")
    assert resp.status_code == 200
    assert resp.json()["nodes"][0]["id"] == "a"
    assert stub.calls == [False]


def test_rebuild_passthrough(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    resp = TestClient(web.app).post("/api/skillmap/graph/rebuild")
    assert resp.status_code == 200
    assert stub.calls == [True]


def test_graph_daemon_not_started(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)
    assert TestClient(web.app).get("/api/skillmap/graph").json() == {"error": "daemon not started"}
