"""POST /api/quiz + /api/quiz/grade — passthrough + guards.

Stub daemon, TestClient without the context manager (no lifespan / no API key),
mirroring test_second_opinion_api.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from salient_tutor import web


class _StubDaemon:
    def __init__(self, quiz_payload=None, grade_payload=None):
        self._quiz = quiz_payload or {"question": "Q?", "answer": "A"}
        self._grade = grade_payload or {"grade": "good", "feedback": "nice", "interval_days": 2}
        self.calls = []

    async def quiz(self, topic):
        self.calls.append(("quiz", topic))
        return self._quiz

    async def grade_quiz(self, topic, question, answer, learner_answer):
        self.calls.append(("grade", topic, learner_answer))
        return self._grade

    def record_review(self, topic, grade):
        self.calls.append(("review", topic, grade))
        if grade not in ("again", "hard", "good", "easy"):
            raise ValueError(f"unknown grade: {grade!r}")
        return {"topic": topic, "grade": grade, "mastery": 0.5, "interval_days": 2}


def test_quiz_passthrough(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    resp = TestClient(web.app).post("/api/quiz", json={"topic": "photosynthesis"})
    assert resp.status_code == 200
    assert resp.json() == {"question": "Q?", "answer": "A"}
    assert stub.calls == [("quiz", "photosynthesis")]


def test_quiz_empty_topic(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    assert TestClient(web.app).post("/api/quiz", json={"topic": "  "}).json() == {
        "error": "no topic"
    }
    assert stub.calls == []  # never dispatched


def test_quiz_grade_passthrough(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    resp = TestClient(web.app).post(
        "/api/quiz/grade",
        json={
            "topic": "photosynthesis",
            "question": "Q?",
            "answer": "A",
            "learner_answer": "chloroplast",
        },
    )
    assert resp.json() == {"grade": "good", "feedback": "nice", "interval_days": 2}
    assert stub.calls == [("grade", "photosynthesis", "chloroplast")]


def test_quiz_daemon_not_started(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)
    assert TestClient(web.app).post("/api/quiz", json={"topic": "x"}).json() == {
        "error": "daemon not started"
    }


# ── /api/review — memory-palace locus grades ride the SM-2 gradebook ──────────


def test_review_passthrough(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    topic = "loci:oauth-pkce-casino/locus-authn"
    resp = TestClient(web.app).post("/api/review", json={"topic": topic, "grade": "good"})
    assert resp.status_code == 200
    assert resp.json()["interval_days"] == 2
    assert stub.calls == [("review", topic, "good")]


def test_review_empty_topic(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    assert TestClient(web.app).post("/api/review", json={"topic": " ", "grade": "good"}).json() == {
        "error": "no topic"
    }
    assert stub.calls == []  # never dispatched


def test_review_bad_grade(monkeypatch):
    stub = _StubDaemon()
    monkeypatch.setattr(web, "daemon", stub)
    r = TestClient(web.app).post("/api/review", json={"topic": "x", "grade": "brilliant"}).json()
    assert "error" in r  # ValueError from record_review surfaced as 200 + error


def test_review_daemon_not_started(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)
    assert TestClient(web.app).post("/api/review", json={"topic": "x", "grade": "good"}).json() == {
        "error": "daemon not started"
    }
