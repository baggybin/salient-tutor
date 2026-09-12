"""Server-owned lesson loop: CHECK → Anchor → Drill graph, mastery gate, SM-2."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from salient_tutor import web
from salient_tutor.daemon import LEARNER_SUBJECT, TutorDaemon
from salient_tutor.lesson import LessonController, assessment_kind_for, phase_after_attempt
from salient_tutor.lesson_store import LessonStore, LessonStoreError


def _stub_author_and_score(daemon, monkeypatch, *, author=None, score=None):
    async def fake(agent, message, *, timeout=120.0, session_id=None):
        if "ASSESSMENT SCORE" in message:
            return score or '{"status":"pass","confidence":0.95,"feedback":"solid why"}'
        return author or '{"question":"Why does the TGS last?","answer":"long-lived SPN password"}'

    monkeypatch.setattr(daemon, "prompt", fake)


def _to_check(controller: LessonController, session_id: str) -> dict:
    controller.advance(session_id)  # diagnose → objective
    controller.advance(session_id)  # objective → model
    return controller.advance(session_id)  # model → issues CHECK


def test_assessment_kind_for_phases() -> None:
    assert assessment_kind_for("model") == "check"
    assert assessment_kind_for("anchor") == "retrieval"
    assert assessment_kind_for("drill") == "apply"
    assert assessment_kind_for("diagnose") is None


def test_phase_after_attempt_graph() -> None:
    check = {"kind": "check"}
    retrieval = {"kind": "retrieval"}
    apply = {"kind": "apply"}
    assert phase_after_attempt(check, "pass") == "anchor"
    assert phase_after_attempt(check, "fail") == "model"
    assert phase_after_attempt(retrieval, "pass") == "drill"
    assert phase_after_attempt(retrieval, "fail") == "model"
    assert phase_after_attempt(apply, "pass") == "reflect"
    assert phase_after_attempt(apply, "fail") == "drill"
    assert phase_after_attempt(check, "unscored") == "awaiting_attempt"


def test_advance_from_model_issues_check_item(tmp_path) -> None:
    controller = LessonController(LessonStore(tmp_path / "lessons.db"))
    session = controller.create_session("custom:x")
    issued = _to_check(controller, session["session_id"])
    assert issued["session"]["phase"] == "awaiting_attempt"
    assert issued["item"]["kind"] == "check"
    assert "reference_answer" not in issued["item"]
    # Cannot walk into awaiting_attempt with no item, then get stuck.
    with pytest.raises(LessonStoreError, match="submit the active"):
        controller.advance(session["session_id"])


def test_cannot_issue_item_during_diagnose(tmp_path) -> None:
    controller = LessonController(LessonStore(tmp_path / "lessons.db"))
    session = controller.create_session("custom:x")
    with pytest.raises(LessonStoreError, match="model, anchor, or drill"):
        controller.issue_item(session["session_id"])


def test_check_pass_then_retrieval_then_apply(tmp_path) -> None:
    controller = LessonController(LessonStore(tmp_path / "lessons.db"))
    session = controller.create_session("custom:x")
    sid = session["session_id"]
    check = _to_check(controller, sid)
    passed_check = controller.record_attempt(
        sid, check["item"]["item_id"], 1, "custom:x", "k-check"
    )
    assert passed_check["session"]["phase"] == "anchor"
    assert passed_check["session"]["active_item_id"] is None

    retrieval = controller.advance(sid)  # anchor → retrieval item
    assert retrieval["item"]["kind"] == "retrieval"
    passed_recall = controller.record_attempt(
        sid, retrieval["item"]["item_id"], 1, "custom:x", "k-recall"
    )
    assert passed_recall["session"]["phase"] == "drill"

    apply_item = controller.advance(sid)  # drill → apply item
    assert apply_item["item"]["kind"] == "apply"
    assert apply_item["item"]["bloom"] == "apply"
    passed_apply = controller.record_attempt(
        sid, apply_item["item"]["item_id"], 1, "custom:x", "k-apply"
    )
    assert passed_apply["session"]["phase"] == "reflect"


def test_mastery_gate_blocks_complete_without_apply_pass(tmp_path) -> None:
    controller = LessonController(LessonStore(tmp_path / "lessons.db"))
    session = controller.create_session("custom:x")
    sid = session["session_id"]
    check = _to_check(controller, sid)
    controller.record_attempt(sid, check["item"]["item_id"], 1, "custom:x", "k-check")
    # Walk teaching phases after CHECK (anchor still needs its item skipped via
    # force-transition would be cheating; instead complete CHECK only and try
    # to finish from elaborate by walking reflect/cards without apply).
    # From anchor, we must issue retrieval — skip by not completing the loop
    # and asserting elaborate is gated even if we somehow got there: walk
    # apply-less path isn't reachable via advance() because anchor/drill issue
    # items. Direct transition:
    controller.store.transition(sid, "elaborate")
    with pytest.raises(LessonStoreError, match="mastery gate"):
        controller.advance(sid)


def test_mastery_gate_allows_complete_after_apply_pass(tmp_path) -> None:
    controller = LessonController(LessonStore(tmp_path / "lessons.db"))
    session = controller.create_session("custom:x")
    sid = session["session_id"]
    check = _to_check(controller, sid)
    controller.record_attempt(sid, check["item"]["item_id"], 1, "custom:x", "a")
    retrieval = controller.advance(sid)
    controller.record_attempt(sid, retrieval["item"]["item_id"], 1, "custom:x", "b")
    apply_item = controller.advance(sid)
    controller.record_attempt(sid, apply_item["item"]["item_id"], 1, "custom:x", "c")
    # reflect → cards → elaborate → completed
    controller.advance(sid)
    controller.advance(sid)
    done = controller.advance(sid)
    assert done["status"] == "completed"
    assert done["phase"] == "completed"


def test_current_session_includes_mastery_stage(tmp_path) -> None:
    store = LessonStore(tmp_path / "lessons.db")
    controller = LessonController(store)
    controller.create_session("custom:x")
    current = controller.current_session()
    assert current is not None
    assert current["mastery_stage"] == "unstarted"


def test_daemon_record_attempt_writes_sm2(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    daemon = TutorDaemon(work_root=tmp_path / "work")
    session = daemon.create_session("custom:photosynthesis")
    sid = session["session_id"]
    asyncio.run(daemon.advance_phase(sid))
    asyncio.run(daemon.advance_phase(sid))
    issued = asyncio.run(daemon.issue_assessment_item(sid))
    result = asyncio.run(
        daemon.record_attempt(sid, issued["item"]["item_id"], 1, "custom:photosynthesis", "sm2-1")
    )
    assert result["attempt"]["scoring_status"] == "pass"
    assert result["review"]["application_status"] == "applied"
    assert result["review"]["requested_grade"] == "good"
    state = daemon.kg.learner_review_state(LEARNER_SUBJECT, "custom:photosynthesis")
    assert state is not None
    assert state["mastery"] > 0


def test_daemon_authors_free_text_check(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    daemon = TutorDaemon(work_root=tmp_path / "work")
    _stub_author_and_score(daemon, monkeypatch)
    sid = daemon.create_session("custom:kerberoast")["session_id"]
    asyncio.run(daemon.advance_phase(sid))
    asyncio.run(daemon.advance_phase(sid))
    issued = asyncio.run(daemon.advance_phase(sid))  # model → authored CHECK
    assert issued["item"]["kind"] == "check"
    assert issued["item"]["prompt"] == "Why does the TGS last?"
    assert issued["item"]["response_type"] == "free_text" or "response_type" not in issued["item"]
    assert "reference_answer" not in issued["item"]
    stored = daemon.lesson_store.get_item(issued["item"]["item_id"], 1)
    assert stored["reference_answer"] == "long-lived SPN password"
    assert stored["response_type"] == "free_text"
    assert stored["generator_version"] == "tutor-author-v1"


def test_daemon_author_fallback_on_bad_json(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    daemon = TutorDaemon(work_root=tmp_path / "work")
    _stub_author_and_score(daemon, monkeypatch, author="not json at all")
    sid = daemon.create_session("custom:x")["session_id"]
    asyncio.run(daemon.advance_phase(sid))
    asyncio.run(daemon.advance_phase(sid))
    issued = asyncio.run(daemon.advance_phase(sid))
    stored = daemon.lesson_store.get_item(issued["item"]["item_id"], 1)
    assert stored["response_type"] == "cloze"
    assert stored["reference_answer"] == "custom:x"


def test_daemon_scores_authored_item(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    daemon = TutorDaemon(work_root=tmp_path / "work")
    _stub_author_and_score(
        daemon, monkeypatch, score='{"status":"fail","confidence":0.9,"feedback":"not the why"}'
    )
    sid = daemon.create_session("custom:kerberoast")["session_id"]
    asyncio.run(daemon.advance_phase(sid))
    asyncio.run(daemon.advance_phase(sid))
    issued = asyncio.run(daemon.advance_phase(sid))
    result = asyncio.run(
        daemon.record_attempt(sid, issued["item"]["item_id"], 1, "it uses port 88", "k1")
    )
    assert result["attempt"]["scoring_status"] == "fail"
    assert result["session"]["phase"] == "model"
    assert "not the why" in result["attempt"]["feedback"]


def test_empty_free_text_fails_without_model(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    daemon = TutorDaemon(work_root=tmp_path / "work")
    _stub_author_and_score(daemon, monkeypatch)
    sid = daemon.create_session("custom:kerberoast")["session_id"]
    asyncio.run(daemon.advance_phase(sid))
    asyncio.run(daemon.advance_phase(sid))
    issued = asyncio.run(daemon.advance_phase(sid))
    result = asyncio.run(daemon.record_attempt(sid, issued["item"]["item_id"], 1, "  ", "empty"))
    assert result["attempt"]["scoring_status"] == "fail"
    assert result["session"]["phase"] == "model"


def test_http_ignores_client_judge_result(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    daemon = TutorDaemon(work_root=tmp_path / "work")
    monkeypatch.setattr(web, "daemon", daemon)
    client = TestClient(web.app)
    sid = client.post("/api/sessions", json={"skill_id": "custom:x"}).json()["session_id"]
    client.post(f"/api/sessions/{sid}/advance", json={"expected_version": 0})
    client.post(f"/api/sessions/{sid}/advance", json={"expected_version": 1})
    issued = client.post(f"/api/sessions/{sid}/items", json={"expected_version": 2}).json()
    # Free-text item isn't the default; POST a cloze attempt with a fake
    # judge_result — the HTTP path must ignore it (default item is cloze so
    # scoring is the topic id, not the judge payload).
    attempt = client.post(
        f"/api/sessions/{sid}/attempts",
        json={
            "item_id": issued["item"]["item_id"],
            "item_version": 1,
            "response": "nope",
            "idempotency_key": "http-1",
            "judge_result": {"status": "pass", "confidence": 0.99},
        },
    )
    assert attempt.status_code == 200
    body = attempt.json()
    assert body["attempt"]["scoring_status"] == "fail"
    assert body["session"]["phase"] == "model"
