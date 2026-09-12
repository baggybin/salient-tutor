from __future__ import annotations

import re
import uuid
from typing import Final

from salient_tutor.lesson_store import IdempotencyConflict, LessonStore, LessonStoreError

PHASES: Final[tuple[str, ...]] = (
    "diagnose",
    "objective",
    "model",
    "awaiting_attempt",
    "anchor",
    "drill",
    "reflect",
    "cards",
    "elaborate",
)
# Teaching-phase walk. model / anchor / drill issue an assessment instead of
# stepping to a bare awaiting_attempt (that wedge had no item to submit).
_TEACH_NEXT: Final[dict[str, str]] = {
    "diagnose": "objective",
    "objective": "model",
    "reflect": "cards",
    "cards": "elaborate",
}
# Continue from these phases issues the matching CHECK / ANCHOR / DRILL item.
_ISSUE_KIND: Final[dict[str, str]] = {
    "model": "check",
    "anchor": "retrieval",
    "drill": "apply",
}
_HOLD_STATUSES: Final[frozenset[str]] = frozenset({"unscored", "ambiguous", "partial"})
_GRADES: Final[frozenset[str]] = frozenset({"again", "hard", "good", "easy"})
_ITEM_KINDS: Final[frozenset[str]] = frozenset({"check", "retrieval", "apply"})


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "topic"


def assessment_kind_for(phase: str) -> str | None:
    """CHECK / ANCHOR-recall / DRILL-apply kind issued from a teaching phase."""
    return _ISSUE_KIND.get(phase)


def phase_after_attempt(item: dict, scoring_status: str) -> str:
    """CHECK / ANCHOR / DRILL graph. Unscored holds the gate; fail CHECK
    re-teaches MODEL instead of skipping to a same-item drill retry."""
    if scoring_status in _HOLD_STATUSES:
        return "awaiting_attempt"
    passed = scoring_status == "pass"
    kind = item.get("kind") or "check"
    if kind == "check":
        return "anchor" if passed else "model"
    if kind == "retrieval":
        return "drill" if passed else "model"
    if kind == "apply":
        return "reflect" if passed else "drill"
    return "anchor" if passed else "model"


class LessonController:
    def __init__(self, store: LessonStore) -> None:
        self.store = store

    def create_session(
        self,
        skill_id: str,
        *,
        srs_topic: str | None = None,
        session_kind: str = "lesson",
        **bindings: str | None,
    ) -> dict:
        if not skill_id.strip():
            raise LessonStoreError("skill_id is required")
        session_id = uuid.uuid4().hex
        # Delayed retrieval is a drill on a known topic — skip diagnose/model.
        phase = "drill" if session_kind == "delayed_retrieval" else "diagnose"
        return self._with_active_item(
            self.store.create_session(
                {
                    "session_id": session_id,
                    "status": "active",
                    "session_kind": session_kind,
                    "skill_id": skill_id,
                    "srs_topic": srs_topic or skill_id,
                    "phase": phase,
                    **bindings,
                },
                idempotency_key=f"create:{session_id}",
            )
        )

    def get_session(self, session_id: str) -> dict:
        session = self.store.get_session(session_id)
        if session is None:
            raise LessonStoreError(f"unknown session: {session_id}")
        return self._with_active_item(session)

    def current_session(self) -> dict | None:
        session = self.store.current_session()
        return self._with_active_item(session) if session else None

    def pause(self, session_id: str, expected_version: int | None = None) -> dict:
        return self._with_active_item(
            self.store.transition(
                session_id,
                self.get_session(session_id)["phase"],
                expected_version=expected_version,
                status="paused",
                event_type="paused",
            )
        )

    def resume(self, session_id: str, expected_version: int | None = None) -> dict:
        return self._with_active_item(
            self.store.transition(
                session_id,
                self.get_session(session_id)["phase"],
                expected_version=expected_version,
                status="active",
                event_type="resumed",
            )
        )

    def abandon(self, session_id: str, expected_version: int | None = None) -> dict:
        return self._with_active_item(
            self.store.transition(
                session_id,
                "abandoned",
                expected_version=expected_version,
                status="abandoned",
                event_type="abandoned",
            )
        )

    def advance(self, session_id: str, expected_version: int | None = None) -> dict:
        session = self.get_session(session_id)
        phase = session["phase"]
        if phase == "awaiting_attempt":
            raise LessonStoreError("submit the active assessment item before advancing")
        if session["status"] != "active":
            raise LessonStoreError("session is not active")
        if phase in _ISSUE_KIND:
            # Issue the CHECK / ANCHOR-recall / DRILL-apply item. Never walk
            # into awaiting_attempt with no item (that session cannot submit
            # or advance).
            return self.issue_item(session_id, expected_version=expected_version)
        if phase == "elaborate":
            if not self.store.session_has_apply_pass(session_id):
                raise LessonStoreError(
                    "mastery gate: demonstrate Apply on a fresh case before completing"
                )
            return self._with_active_item(
                self.store.transition(
                    session_id,
                    "completed",
                    expected_version=expected_version,
                    status="completed",
                    event_type="completed",
                )
            )
        next_phase = _TEACH_NEXT.get(phase)
        if next_phase is None:
            raise LessonStoreError(f"phase cannot advance: {phase}")
        return self._with_active_item(
            self.store.transition(
                session_id,
                next_phase,
                expected_version=expected_version,
                status="active",
                event_type="phase_changed",
            )
        )

    def issue_item(
        self, session_id: str, *, item: dict | None = None, expected_version: int | None = None
    ) -> dict:
        session = self.get_session(session_id)
        if session["status"] != "active":
            raise LessonStoreError("session is not active")
        if session["active_item_id"]:
            # Resolve the actual stored version rather than assuming 1 — an item
            # authored at version != 1 would otherwise read as missing and get
            # silently replaced by a fresh default item, orphaning the in-flight
            # assessment.
            existing = self.store.get_latest_item(session["active_item_id"])
            if existing:
                return {"item": self._learner_item(existing), "session": session}
        phase = session["phase"]
        if phase not in _ISSUE_KIND and phase != "awaiting_attempt":
            raise LessonStoreError("issue an assessment from model, anchor, or drill")
        kind = (item or {}).get("kind") if item else None
        if kind not in _ITEM_KINDS:
            kind = _ISSUE_KIND.get(phase) or (
                "apply" if session["session_kind"] == "delayed_retrieval" else "check"
            )
        source = item or self._default_item(session, kind)
        if "kind" not in source:
            source["kind"] = kind
        self._validate_item(source)
        self.store.save_item(source)
        snapshot = self.store.set_active_item(
            session_id, source["item_id"], expected_version=expected_version
        )
        return {"item": self._learner_item(source), "session": self._with_active_item(snapshot)}

    def record_attempt(
        self,
        session_id: str,
        item_id: str,
        item_version: int,
        response: str,
        idempotency_key: str,
        *,
        hints_used: int = 0,
        judge_result: dict | None = None,
    ) -> dict:
        session = self.get_session(session_id)
        replayed = self._replayed_attempt(session_id, idempotency_key)
        if replayed is not None:
            return {"attempt": replayed, "session": session}
        if session["phase"] != "awaiting_attempt" or session["active_item_id"] != item_id:
            raise LessonStoreError("the submitted item is not the active assessment")
        item = self.store.get_item(item_id, item_version)
        if item is None:
            raise LessonStoreError("unknown assessment item version")
        score = self._score(item, response, judge_result)
        next_phase = phase_after_attempt(item, score["scoring_status"])
        attempt_id = uuid.uuid4().hex
        # Atomic: attempt row + idempotency event + phase transition commit in a
        # single transaction, so a crash between writes can't leave a duplicate
        # attempt or a wedged phase.
        try:
            snapshot = self.store.record_attempt_and_transition(
                {
                    "attempt_id": attempt_id,
                    "session_id": session_id,
                    "item_id": item_id,
                    "item_version": item_version,
                    "response": response,
                    "hints_used": hints_used,
                    **score,
                },
                idempotency_key=idempotency_key,
                next_phase=next_phase,
                event_type="assessment_scored",
                event_payload={"status": score["scoring_status"], "phase": next_phase},
            )
        except IdempotencyConflict:
            # A concurrent same-key submit won the race between our read-guard
            # above and the transaction: return its attempt, not a duplicate.
            replayed = self._replayed_attempt(session_id, idempotency_key)
            if replayed is not None:
                return {"attempt": replayed, "session": self.get_session(session_id)}
            raise
        attempt = self.store.get_attempt(attempt_id)
        # mastery_stage is derived read-only from this attempt on read
        # (get_session injects it); no written column to update.
        return {"attempt": attempt, "session": self._with_active_item(snapshot)}

    def _replayed_attempt(self, session_id: str, idempotency_key: str) -> dict | None:
        """The attempt already recorded under this idempotency key, if any."""
        for event in self.store.events(session_id):
            if event.get("idempotency_key") == idempotency_key:
                attempt_id = event.get("payload", {}).get("attempt_id")
                if attempt_id:
                    attempt = self.store.get_attempt(attempt_id)
                    if attempt:
                        return attempt
        return None

    def _with_active_item(self, session: dict) -> dict:
        """Attach the learner-facing active item (no reference answer)."""
        item_id = session.get("active_item_id")
        if not item_id:
            session["active_item"] = None
            return session
        existing = self.store.get_latest_item(item_id)
        session["active_item"] = self._learner_item(existing) if existing else None
        return session

    @staticmethod
    def _default_item(session: dict, kind: str) -> dict:
        skill = session["skill_id"]
        bloom, prompt = {
            "check": (
                "understand",
                f"What topic are you studying? Reply with the topic id `{skill}`.",
            ),
            "retrieval": (
                "remember",
                f"Recall the topic. Reply with the topic id `{skill}`.",
            ),
            "apply": (
                "apply",
                f"Apply `{skill}` to a fresh case. For this default item, reply with the topic id.",
            ),
        }.get(
            kind,
            ("understand", f"What topic are you studying? Reply with the topic id `{skill}`."),
        )
        return {
            "item_id": f"item-{uuid.uuid4().hex}",
            "version": 1,
            "skill_id": skill,
            "kind": kind,
            "bloom": bloom,
            "response_type": "cloze",
            "prompt": prompt,
            "options": [],
            "rubric": {
                "criteria": [
                    {"id": "core", "description": "matches the topic id", "required": True}
                ]
            },
            "reference_evidence": "server-authored default item",
            "reference_answer": skill,
            "provenance": [],
            "generator_version": "controller-v1",
            "scorer_version": "deterministic-v1",
        }

    @staticmethod
    def _learner_item(item: dict) -> dict:
        return {
            key: value
            for key, value in item.items()
            if key not in {"reference_answer", "reference_evidence"}
        }

    @staticmethod
    def _validate_item(item: dict) -> None:
        required = {
            "item_id",
            "version",
            "skill_id",
            "kind",
            "bloom",
            "response_type",
            "prompt",
            "rubric",
            "reference_answer",
        }
        missing = required - item.keys()
        if missing:
            raise LessonStoreError(f"assessment item missing fields: {', '.join(sorted(missing))}")
        if item["response_type"] not in {"free_text", "multiple_choice", "cloze"}:
            raise LessonStoreError("unsupported assessment response type")
        if item.get("kind") not in _ITEM_KINDS:
            raise LessonStoreError("unsupported assessment kind")
        if not isinstance(item["rubric"], dict) or not isinstance(
            item["rubric"].get("criteria", []), list
        ):
            raise LessonStoreError("assessment rubric must contain criteria")

    @staticmethod
    def _score(item: dict, response: str, judge_result: dict | None = None) -> dict:
        if item["response_type"] == "free_text":
            return LessonController._score_judge(judge_result)
        answer = str(item["reference_answer"]).strip().casefold()
        actual = response.strip().casefold()
        status = "pass" if actual and actual == answer else "fail"
        return {
            "score_by_criterion": {"core": 1.0 if status == "pass" else 0.0},
            "scoring_status": status,
            "scorer_version": "deterministic-v1",
            "feedback": "Correct retrieval."
            if status == "pass"
            else "Try the item again after reviewing the model.",
            "next_action": "advance" if status == "pass" else "remediate",
        }

    @staticmethod
    def _score_judge(result: dict | None) -> dict:
        if not isinstance(result, dict) or result.get("status") not in {
            "pass",
            "partial",
            "fail",
            "ambiguous",
            "unscored",
        }:
            return {
                "score_by_criterion": {},
                "scoring_status": "unscored",
                "scorer_version": "judge-v1",
                "feedback": "This response could not be scored yet.",
                "next_action": "retry",
            }
        confidence = result.get("confidence")
        if not isinstance(confidence, (int, float)) or confidence < 0.80:
            status = "unscored"
        else:
            status = result["status"]
        criteria = result.get("criteria")
        if not isinstance(criteria, list):
            criteria = []
        scores = {
            str(row["id"]): float(row["score"])
            for row in criteria
            if isinstance(row, dict)
            and row.get("id")
            and isinstance(row.get("score"), (int, float))
        }
        return {
            "score_by_criterion": scores,
            "scoring_status": status,
            "scorer_version": "judge-v1",
            "feedback": str(result.get("feedback") or ""),
            "next_action": str(
                result.get("next_action") or ("advance" if status == "pass" else "retry")
            ),
        }

    @staticmethod
    def grade_for_attempt(attempt: dict) -> str | None:
        if attempt["scoring_status"] in {"unscored", "ambiguous", "partial"}:
            return None
        if attempt["scoring_status"] != "pass":
            return "again"
        if attempt.get("hints_used", 0):
            return "hard"
        return "good"
