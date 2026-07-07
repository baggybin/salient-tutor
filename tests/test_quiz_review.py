"""Retrieval micro-quiz — record_review (deterministic SM-2) + quiz/grade orchestration.

record_review runs against a REAL KnowledgeGraph on a tmp work_root (no LLM);
quiz/grade_quiz drive the tutor via a stubbed prompt.
"""

from __future__ import annotations

import asyncio

from salient_tutor.daemon import LEARNER_SUBJECT, TutorDaemon


def _daemon(tmp_path, monkeypatch, *, reply=None, raises=False):
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    d = TutorDaemon(work_root=tmp_path / "work")
    d.agent_configs = {"tutor": {}}
    d.last_prompt = None

    async def _fake_prompt(agent, message, *, timeout=120.0):
        d.last_prompt = message
        if raises:
            raise RuntimeError("tutor down")
        return reply

    monkeypatch.setattr(d, "prompt", _fake_prompt)
    return d


# ── record_review (deterministic, real KG) ───────────────────────────────────


def test_record_review_writes_and_schedules(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    out = d.record_review("photosynthesis", "good")
    assert out["topic"] == "photosynthesis"
    assert out["grade"] == "good"
    assert out["mastery"] > 0
    assert out["interval_days"] > 0
    assert out["predicate"] in ("strong_topic", "weak_topic")
    # persisted under learner:op and readable back
    state = d.kg.learner_review_state(LEARNER_SUBJECT, "photosynthesis")
    assert state is not None
    assert state["mastery"] == out["mastery"]
    assert state["review_due"] is not None


def test_record_review_good_grows_interval(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    first = d.record_review("mitosis", "good")
    second = d.record_review("mitosis", "good")
    assert second["interval_days"] >= first["interval_days"]
    assert second["mastery"] >= first["mastery"]


def test_record_review_again_is_a_lapse(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    d.record_review("osmosis", "easy")  # build some mastery
    strong = d.kg.learner_review_state(LEARNER_SUBJECT, "osmosis")["mastery"]
    lapse = d.record_review("osmosis", "again")
    assert lapse["mastery"] < strong  # mastery dropped
    assert lapse["interval_days"] <= 1.0  # interval reset to the lapse floor


def test_record_review_rejects_bad_grade(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    try:
        d.record_review("x", "brilliant")
    except ValueError:
        return
    raise AssertionError("expected ValueError on an unknown grade")


# ── review-event log (Phase-0 scheduling telemetry) ──────────────────────────


def test_record_review_appends_to_log(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    out = d.record_review("photosynthesis", "good")
    events = d.review_log()
    assert len(events) == 1
    e = events[0]
    # the log captures the FULL before/after the KG overwrite discards
    assert e["topic"] == "photosynthesis"
    assert e["grade"] == "good"
    assert e["mastery_before"] is None  # first sight, no prior state
    assert e["mastery_after"] == out["mastery"]
    assert e["prev_interval_days"] is None
    assert e["interval_days"] == out["interval_days"]
    assert e["review_due"] == out["review_due"]


def test_review_log_accumulates_and_captures_prior_state(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    first = d.record_review("mitosis", "good")
    d.record_review("mitosis", "good")
    events = d.review_log(topic="mitosis")
    assert len(events) == 2  # append-only — the second review does NOT overwrite the first
    # the second event's "before" equals the first's "after" (history preserved)
    assert events[1]["mastery_before"] == first["mastery"]
    assert events[1]["prev_interval_days"] == first["interval_days"]


def test_review_log_filters_by_topic_and_limit(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch)
    d.record_review("a", "good")
    d.record_review("b", "hard")
    d.record_review("a", "easy")
    assert [e["topic"] for e in d.review_log()] == ["a", "b", "a"]  # oldest→newest
    assert len(d.review_log(topic="a")) == 2
    assert len(d.review_log(limit=1)) == 1
    assert d.review_log(limit=1)[0]["topic"] == "a"  # most recent kept


def test_reviewlog_read_missing_file_is_empty(tmp_path):
    from salient_tutor import reviewlog

    assert reviewlog.read(tmp_path / "work") == []


def test_reviewlog_summarize_recall_at_due(tmp_path, monkeypatch):
    from salient_tutor import reviewlog

    assert reviewlog.summarize([])["recall_rate"] is None
    d = _daemon(tmp_path, monkeypatch)
    d.record_review("a", "good")  # first sight — no prior schedule (excluded from rate)
    d.record_review("a", "again")  # due, failed
    d.record_review("a", "good")  # due, recalled
    d.record_review("b", "easy")  # first sight
    s = reviewlog.summarize(d.review_log())
    assert s["total"] == 4
    assert s["topics"] == 2
    assert s["reviews_at_due"] == 2  # only the two 'a' reviews had a prior schedule
    assert s["recall_rate"] == 0.5  # 1 of 2 due reviews recalled (not 'again')
    assert s["grades"] == {"again": 1, "hard": 0, "good": 2, "easy": 1}


# ── quiz (question generation) ────────────────────────────────────────────────


def test_quiz_parses_question(tmp_path, monkeypatch):
    d = _daemon(
        tmp_path,
        monkeypatch,
        reply='{"question": "Which organelle performs photosynthesis?", "answer": "chloroplast"}',
    )
    out = asyncio.run(d.quiz("photosynthesis"))
    assert out == {"question": "Which organelle performs photosynthesis?", "answer": "chloroplast"}


def test_quiz_empty_topic(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply='{"question":"q","answer":"a"}')
    assert asyncio.run(d.quiz("   ")) == {"error": "no topic"}


def test_quiz_bad_json(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply="here you go: ...")
    assert "error" in asyncio.run(d.quiz("photosynthesis"))


# ── grade_quiz (grade + record) ───────────────────────────────────────────────


def test_grade_quiz_records_review(tmp_path, monkeypatch):
    d = _daemon(
        tmp_path, monkeypatch, reply='{"grade": "good", "feedback": "Right — chloroplast."}'
    )
    out = asyncio.run(d.grade_quiz("photosynthesis", "Q?", "chloroplast", "chloroplast"))
    assert out["grade"] == "good"
    assert out["feedback"].startswith("Right")
    assert out["interval_days"] > 0
    # the review actually landed in the gradebook
    assert d.kg.learner_review_state(LEARNER_SUBJECT, "photosynthesis") is not None


def test_grade_quiz_unusable_grade_records_nothing(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply='{"grade": "meh", "feedback": "unclear"}')
    out = asyncio.run(d.grade_quiz("photosynthesis", "Q?", "a", "?"))
    assert out["grade"] is None
    assert out["feedback"] == "unclear"
    assert d.kg.learner_review_state(LEARNER_SUBJECT, "photosynthesis") is None  # no write


def test_grade_quiz_tutor_failure(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, raises=True)
    out = asyncio.run(d.grade_quiz("photosynthesis", "Q?", "a", "?"))
    assert out["grade"] is None
    assert "error" in out
