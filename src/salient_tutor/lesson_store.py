from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

SCHEMA_VERSION: Final = 3


class LessonStoreError(RuntimeError):
    pass


class SessionConflict(LessonStoreError):
    pass


class IdempotencyConflict(LessonStoreError):
    pass


def canonical_curriculum_skill(track_id: str, module_id: str, topic_id: str) -> str:
    return f"curriculum:track:{track_id}:module:{module_id}:topic:{topic_id}"


def canonical_study_skill(project_id: str, section_id: str) -> str:
    return f"study:{project_id}:sec:{section_id}"


def canonical_custom_skill(slug: str) -> str:
    return f"custom:{slug.strip().lower().replace(' ', '-')}"


def derive_mastery_stage(session: dict | None, latest_attempt: dict | None = None) -> str:
    """Compute a session's mastery stage read-only from its latest attempt.

    Replaces the written ``sessions.mastery_stage`` column so there is a single
    authority for cross-session/topic mastery (the KG SM-2 gradebook) and this
    per-session derivation for attempt outcomes. Returns one of:
    ``unstarted`` / ``provisional_mastery`` / ``durable_mastery`` /
    ``remediation_queued``."""
    if not session or not latest_attempt:
        return "unstarted"
    passed = latest_attempt.get("scoring_status") == "pass"
    is_delayed = session.get("session_kind") == "delayed_retrieval"
    if passed and is_delayed:
        return "durable_mastery"
    if passed:
        return "provisional_mastery"
    if is_delayed:
        return "remediation_queued"
    return "unstarted"


# ── Schema migrations ──────────────────────────────────────────────────────
# A fresh db (version 0) is created at the current shape by CREATE-IF-NOT-EXISTS,
# so only pre-existing DBs at version >= 1 are walked forward through these steps.
# Each step is (from_version, to_version, description, apply(db)).

_MigrationStep = tuple[int, int, str, Callable[[sqlite3.Connection], None]]


def _migrate_v1_to_v2(db: sqlite3.Connection) -> None:
    """v1 carried UNIQUE(session_id, item_id, item_version) on attempts, which
    made a post-fail retry impossible: the correct resubmit collided and
    save_attempt returned the stale failed row, trapping the learner in an
    unwinnable drill loop. attempts is append-only and idempotency is enforced
    by session_events(idempotency_key), so rebuild the table without the
    constraint, preserving history."""
    db.executescript(
        """
        ALTER TABLE attempts RENAME TO attempts_legacy_v1;
        CREATE TABLE attempts (
            attempt_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            item_id TEXT NOT NULL,
            item_version INTEGER NOT NULL,
            response TEXT NOT NULL,
            hints_used INTEGER NOT NULL DEFAULT 0,
            score_by_criterion TEXT NOT NULL,
            scoring_status TEXT NOT NULL,
            scorer_version TEXT NOT NULL,
            feedback TEXT NOT NULL,
            next_action TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        INSERT INTO attempts SELECT * FROM attempts_legacy_v1;
        DROP TABLE attempts_legacy_v1;
        """
    )


def _migrate_v2_to_v3(db: sqlite3.Connection) -> None:
    """v2 stored per-session ``mastery_stage`` as a written column, which
    drifted from the KG SM-2 gradebook and the curriculum-list derivation.
    Mastery is now derived read-only from attempt outcomes (see
    ``derive_mastery_stage``), so drop the column. Idempotent: a no-op if the
    column is already gone (e.g. a fresh db created at the v3 shape)."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}
    if "mastery_stage" in columns:
        db.execute("ALTER TABLE sessions DROP COLUMN mastery_stage")


_MIGRATION_STEPS: Final[tuple[_MigrationStep, ...]] = (
    (
        1,
        2,
        "drop UNIQUE(session_id,item_id,item_version) on attempts so post-fail retries can append",
        _migrate_v1_to_v2,
    ),
    (
        2,
        3,
        "drop sessions.mastery_stage (now derived read-only from attempt outcomes)",
        _migrate_v2_to_v3,
    ),
)


class LessonStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Default (no migration applied yet); _migrate overwrites on initialize.
        self._migration_info: dict = {
            "from_version": 0,
            "to_version": SCHEMA_VERSION,
            "applied": [],
        }
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # Concurrent writers (web + CLI, or two requests) would otherwise get an
        # immediate "database is locked"; wait up to 5s for the write lock.
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            version = int(db.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise LessonStoreError(f"unsupported lessons.db schema version: {version}")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    session_kind TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    srs_topic TEXT NOT NULL,
                    track_id TEXT,
                    module_id TEXT,
                    topic_id TEXT,
                    study_project_id TEXT,
                    section_id TEXT,
                    phase TEXT NOT NULL,
                    phase_version INTEGER NOT NULL DEFAULT 0,
                    active_item_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    idempotency_key TEXT,
                    UNIQUE(session_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS assessment_items (
                    item_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    skill_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    bloom TEXT NOT NULL,
                    response_type TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    options TEXT NOT NULL,
                    rubric TEXT NOT NULL,
                    reference_evidence TEXT NOT NULL,
                    reference_answer TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    generator_version TEXT NOT NULL,
                    scorer_version TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(item_id, version)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    item_id TEXT NOT NULL,
                    item_version INTEGER NOT NULL,
                    response TEXT NOT NULL,
                    hints_used INTEGER NOT NULL DEFAULT 0,
                    score_by_criterion TEXT NOT NULL,
                    scoring_status TEXT NOT NULL,
                    scorer_version TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_applications (
                    idempotency_key TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    srs_topic TEXT NOT NULL,
                    requested_grade TEXT NOT NULL,
                    application_status TEXT NOT NULL,
                    scheduler_result TEXT NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cards (
                    card_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    skill_id TEXT NOT NULL,
                    source_item_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    card_type TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    srs_topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(card_id, version)
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    agent_name TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    duration_ms REAL,
                    error TEXT,
                    output_hash TEXT,
                    provenance TEXT NOT NULL
                );
                """
            )
            self._migrate(db, version)
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate(self, db: sqlite3.Connection, from_version: int) -> None:
        """Apply ordered, idempotent migrations from an existing db's version up
        to SCHEMA_VERSION, recording what was applied. A fresh db (version 0) is
        already at the current shape via the CREATE-IF-NOT-EXISTS script above,
        so only pre-existing versions (>= 1) are walked forward."""
        applied: list[dict] = []
        if from_version >= 1:
            for step_from, step_to, description, apply_fn in _MIGRATION_STEPS:
                if step_from >= from_version and step_to <= SCHEMA_VERSION:
                    apply_fn(db)
                    applied.append({"from": step_from, "to": step_to, "description": description})
        self._migration_info = {
            "from_version": from_version,
            "to_version": SCHEMA_VERSION,
            "applied": applied,
        }

    @staticmethod
    def _json(value: dict | list) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        result = dict(row)
        for key in (
            "options",
            "rubric",
            "provenance",
            "score_by_criterion",
            "scheduler_result",
            "payload",
        ):
            if key in result:
                result[key] = json.loads(result[key])
        return result

    def create_session(self, session: dict, *, idempotency_key: str | None = None) -> dict:
        now = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session["session_id"],
                    session["status"],
                    session["session_kind"],
                    session["skill_id"],
                    session["srs_topic"],
                    session.get("track_id"),
                    session.get("module_id"),
                    session.get("topic_id"),
                    session.get("study_project_id"),
                    session.get("section_id"),
                    session["phase"],
                    0,
                    None,
                    now,
                    now,
                ),
            )
            self._event(
                db, session["session_id"], "created", {"phase": session["phase"]}, idempotency_key
            )
        return self.get_session(session["session_id"]) or {}

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                return None
            session = self._row(row)
            # mastery_stage is derived read-only from the latest attempt (the
            # written column was dropped in v3) — inject it so the session dict
            # keeps its contract for callers that read session["mastery_stage"].
            # rowid tiebreak: created_at is time.time(), so two quick attempts
            # can share a timestamp — insertion order must break the tie.
            latest = db.execute(
                "SELECT * FROM attempts WHERE session_id=? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            session["mastery_stage"] = derive_mastery_stage(session, self._row(latest))
            return session

    def current_session(self) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE status IN ('active','paused') ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return self._row(row)

    def events(self, session_id: str) -> list[dict]:
        with self._connect() as db:
            return [
                self._row(row) or {}
                for row in db.execute(
                    "SELECT * FROM session_events WHERE session_id=? ORDER BY event_id",
                    (session_id,),
                )
            ]

    def transition(
        self,
        session_id: str,
        phase: str,
        *,
        expected_version: int | None = None,
        status: str | None = None,
        event_type: str = "phase_changed",
        payload: dict | None = None,
    ) -> dict:
        now = time.time()
        with self._connect() as db:
            current = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if current is None:
                raise LessonStoreError(f"unknown session: {session_id}")
            if expected_version is not None and current["phase_version"] != expected_version:
                raise SessionConflict(
                    f"session {session_id} is at version {current['phase_version']}"
                )
            next_status = status or current["status"]
            base_version = current["phase_version"]
            new_version = base_version + 1
            # Compare-and-swap: the WHERE re-checks the version the SELECT read,
            # so two writers that both passed the check above still serialize —
            # the loser's UPDATE matches zero rows and raises, instead of a
            # silent lost update with no 409.
            cursor = db.execute(
                "UPDATE sessions SET phase=?, status=?, phase_version=?, updated_at=? "
                "WHERE session_id=? AND phase_version=?",
                (phase, next_status, new_version, now, session_id, base_version),
            )
            if cursor.rowcount != 1:
                raise SessionConflict(f"session {session_id} changed concurrently")
            self._event(db, session_id, event_type, payload or {"phase": phase}, None)
        return self.get_session(session_id) or {}

    def set_active_item(
        self, session_id: str, item_id: str, *, expected_version: int | None = None
    ) -> dict:
        now = time.time()
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                raise LessonStoreError(f"unknown session: {session_id}")
            if expected_version is not None and row["phase_version"] != expected_version:
                raise SessionConflict(f"session {session_id} is at version {row['phase_version']}")
            base_version = row["phase_version"]
            version = base_version + 1
            cursor = db.execute(
                "UPDATE sessions SET phase='awaiting_attempt', active_item_id=?, phase_version=?, updated_at=? "
                "WHERE session_id=? AND phase_version=?",
                (item_id, version, now, session_id, base_version),
            )
            if cursor.rowcount != 1:
                raise SessionConflict(f"session {session_id} changed concurrently")
            self._event(db, session_id, "item_issued", {"item_id": item_id}, None)
        return self.get_session(session_id) or {}

    def save_item(self, item: dict) -> dict:
        with self._connect() as db:
            db.execute(
                """INSERT INTO assessment_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item["item_id"],
                    item["version"],
                    item["skill_id"],
                    item["kind"],
                    item["bloom"],
                    item["response_type"],
                    item["prompt"],
                    self._json(item.get("options", [])),
                    self._json(item.get("rubric", {})),
                    item.get("reference_evidence", ""),
                    item.get("reference_answer", ""),
                    self._json(item.get("provenance", [])),
                    item.get("generator_version", "manual"),
                    item.get("scorer_version", "deterministic-v1"),
                    time.time(),
                ),
            )
        return item

    def get_item(self, item_id: str, version: int) -> dict | None:
        with self._connect() as db:
            return self._row(
                db.execute(
                    "SELECT * FROM assessment_items WHERE item_id=? AND version=?",
                    (item_id, version),
                ).fetchone()
            )

    def get_latest_item(self, item_id: str) -> dict | None:
        with self._connect() as db:
            return self._row(
                db.execute(
                    "SELECT * FROM assessment_items WHERE item_id=? ORDER BY version DESC LIMIT 1",
                    (item_id,),
                ).fetchone()
            )

    def save_attempt(self, attempt: dict) -> dict:
        # Append-only: every submission is its own attempt row (attempt_id PK).
        # A post-fail retry MUST record a new scored attempt — deduping on
        # (session,item,version) here is what trapped learners in an unwinnable
        # drill loop. Request idempotency is enforced upstream by the
        # session_events(idempotency_key) guard in LessonController.record_attempt.
        with self._connect() as db:
            db.execute(
                """INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attempt["attempt_id"],
                    attempt["session_id"],
                    attempt["item_id"],
                    attempt["item_version"],
                    attempt["response"],
                    attempt.get("hints_used", 0),
                    self._json(attempt.get("score_by_criterion", {})),
                    attempt["scoring_status"],
                    attempt.get("scorer_version", "deterministic-v1"),
                    attempt.get("feedback", ""),
                    attempt.get("next_action", "retry"),
                    time.time(),
                ),
            )
        return self.get_attempt(attempt["attempt_id"]) or {}

    def get_attempt(self, attempt_id: str) -> dict | None:
        with self._connect() as db:
            return self._row(
                db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            )

    def record_attempt_and_transition(
        self,
        attempt: dict,
        *,
        idempotency_key: str,
        next_phase: str,
        event_type: str = "assessment_scored",
        event_payload: dict | None = None,
    ) -> dict:
        """Record a scored attempt, its idempotency event, and the phase
        transition in ONE transaction.

        Previously these were three independent connections (save_attempt →
        _event → transition), so a crash between the attempt INSERT and the
        idempotency-event INSERT left a committed attempt with no replay guard
        — a same-key retry would re-score and append a duplicate. Folding all
        three writes into one connection's transaction makes the turn atomic:
        on any failure the context manager rolls everything back. Returns the
        updated session. Raises SessionConflict if the phase_version changed
        concurrently (compare-and-swap loser), and IdempotencyConflict if the
        idempotency key was already recorded — the OR-IGNORE alone would
        silently drop the replay marker while still committing a duplicate
        attempt, so a zero rowcount aborts (and rolls back) the whole turn."""
        now = time.time()
        with self._connect() as db:
            db.execute(
                """INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attempt["attempt_id"],
                    attempt["session_id"],
                    attempt["item_id"],
                    attempt["item_version"],
                    attempt["response"],
                    attempt.get("hints_used", 0),
                    self._json(attempt.get("score_by_criterion", {})),
                    attempt["scoring_status"],
                    attempt.get("scorer_version", "deterministic-v1"),
                    attempt.get("feedback", ""),
                    attempt.get("next_action", "retry"),
                    now,
                ),
            )
            # Idempotency guard: a same-key event already on record means this
            # is a replay that slipped past the controller's read-guard (e.g.
            # two concurrent submits). Abort so the attempt INSERT above rolls
            # back — otherwise it would commit unguarded, with no event row
            # pointing at it.
            inserted = self._event(
                db,
                attempt["session_id"],
                "attempt_recorded",
                {"attempt_id": attempt["attempt_id"]},
                idempotency_key,
            )
            if inserted == 0:
                raise IdempotencyConflict(
                    f"idempotency key already recorded for session {attempt['session_id']}"
                )
            current = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (attempt["session_id"],)
            ).fetchone()
            if current is None:
                raise LessonStoreError(f"unknown session: {attempt['session_id']}")
            base_version = current["phase_version"]
            new_version = base_version + 1
            # Compare-and-swap: the WHERE re-checks phase_version so two
            # concurrent writers serialize — the loser's UPDATE matches zero
            # rows and raises instead of a silent lost update.
            cursor = db.execute(
                "UPDATE sessions SET phase=?, status=?, phase_version=?, updated_at=? "
                "WHERE session_id=? AND phase_version=?",
                (
                    next_phase,
                    current["status"],
                    new_version,
                    now,
                    attempt["session_id"],
                    base_version,
                ),
            )
            if cursor.rowcount != 1:
                raise SessionConflict(f"session {attempt['session_id']} changed concurrently")
            self._event(
                db,
                attempt["session_id"],
                event_type,
                event_payload or {"phase": next_phase},
                None,
            )
        return self.get_session(attempt["session_id"]) or {}

    def save_review_application(self, application: dict) -> dict:
        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM review_applications WHERE idempotency_key=?",
                (application["idempotency_key"],),
            ).fetchone()
            if existing:
                return self._row(existing) or {}
            db.execute(
                "INSERT INTO review_applications VALUES (?,?,?,?,?,?,?,?)",
                (
                    application["idempotency_key"],
                    application["attempt_id"],
                    application["srs_topic"],
                    application["requested_grade"],
                    application["application_status"],
                    self._json(application.get("scheduler_result", {})),
                    application.get("error"),
                    time.time(),
                ),
            )
        return self.get_review_application(application["idempotency_key"]) or {}

    def get_review_application(self, idempotency_key: str) -> dict | None:
        with self._connect() as db:
            return self._row(
                db.execute(
                    "SELECT * FROM review_applications WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone()
            )

    def save_card(self, card: dict) -> dict:
        with self._connect() as db:
            db.execute(
                "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    card["card_id"],
                    card["version"],
                    card["skill_id"],
                    card["source_item_id"],
                    card["question"],
                    card["answer"],
                    card["card_type"],
                    self._json(card.get("provenance", [])),
                    card["srs_topic"],
                    card.get("status", "active"),
                    time.time(),
                ),
            )
        return self.get_card(card["card_id"], card["version"]) or {}

    def get_card(self, card_id: str, version: int | None = None) -> dict | None:
        with self._connect() as db:
            if version is None:
                row = db.execute(
                    "SELECT * FROM cards WHERE card_id=? ORDER BY version DESC LIMIT 1", (card_id,)
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM cards WHERE card_id=? AND version=?", (card_id, version)
                ).fetchone()
            return self._row(row)

    def list_cards(self, *, skill_id: str | None = None) -> list[dict]:
        with self._connect() as db:
            if skill_id:
                rows = db.execute(
                    "SELECT * FROM cards WHERE skill_id=? ORDER BY card_id, version", (skill_id,)
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM cards ORDER BY card_id, version").fetchall()
            return [self._row(row) or {} for row in rows]

    def update_card_status(self, card_id: str, version: int, status: str) -> dict:
        if status not in {"draft", "active", "retired", "superseded"}:
            raise LessonStoreError(f"invalid card status: {status}")
        with self._connect() as db:
            db.execute(
                "UPDATE cards SET status=? WHERE card_id=? AND version=?",
                (status, card_id, version),
            )
        return self.get_card(card_id, version) or {}

    def schema_version(self) -> int:
        with self._connect() as db:
            return int(db.execute("PRAGMA user_version").fetchone()[0])

    def migration_report(self) -> dict:
        with self._connect() as db:
            names = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            counts = {
                name: int(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
                for name in names
            }
        return {
            "database": str(self.path),
            "schema_version": self.schema_version(),
            "from_version": self._migration_info["from_version"],
            "to_version": self._migration_info["to_version"],
            "migrations_applied": self._migration_info["applied"],
            "tables": counts,
        }

    def start_agent_run(
        self,
        session_id: str | None,
        agent_name: str,
        model: str,
        request_type: str,
        provenance: list[dict] | None = None,
    ) -> dict:
        import uuid

        run_id = uuid.uuid4().hex
        started = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT INTO agent_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    session_id,
                    agent_name,
                    model,
                    request_type,
                    "running",
                    started,
                    None,
                    None,
                    None,
                    None,
                    self._json(provenance or []),
                ),
            )
        return self.get_agent_run(run_id) or {}

    def finish_agent_run(
        self,
        run_id: str,
        status: str,
        *,
        output: str = "",
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> dict:
        with self._connect() as db:
            row = db.execute(
                "SELECT started_at FROM agent_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise LessonStoreError(f"unknown agent run: {run_id}")
            ended = time.time()
            elapsed = duration_ms if duration_ms is not None else (ended - row["started_at"]) * 1000
            digest = hashlib.sha256(output.encode("utf-8")).hexdigest() if output else None
            db.execute(
                "UPDATE agent_runs SET status=?, ended_at=?, duration_ms=?, error=?, output_hash=? WHERE run_id=?",
                (status, ended, elapsed, error, digest, run_id),
            )
        return self.get_agent_run(run_id) or {}

    def get_agent_run(self, run_id: str) -> dict | None:
        with self._connect() as db:
            return self._row(
                db.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
            )

    def analytics(self) -> dict:
        with self._connect() as db:
            attempts = {
                row["scoring_status"]: row["count"]
                for row in db.execute(
                    "SELECT scoring_status, COUNT(*) AS count FROM attempts GROUP BY scoring_status"
                )
            }
            hints = int(
                db.execute("SELECT COALESCE(SUM(hints_used), 0) FROM attempts").fetchone()[0]
            )
            # mastery_stage is derived read-only (no column since v3): join each
            # session to its latest attempt and bucket the derived stage in
            # Python. Single correlated-subquery join — no N+1.
            stages: dict[str, int] = {}
            for row in db.execute(
                "SELECT s.session_kind, a.scoring_status FROM sessions s "
                "LEFT JOIN attempts a ON a.attempt_id = ("
                " SELECT attempt_id FROM attempts WHERE session_id = s.session_id "
                " ORDER BY created_at DESC, rowid DESC LIMIT 1)"
            ).fetchall():
                latest = (
                    {"scoring_status": row["scoring_status"]} if row["scoring_status"] else None
                )
                stage = derive_mastery_stage({"session_kind": row["session_kind"]}, latest)
                stages[stage] = stages.get(stage, 0) + 1
            run_status = {
                row["status"]: row["count"]
                for row in db.execute(
                    "SELECT status, COUNT(*) AS count FROM agent_runs GROUP BY status"
                )
            }
            total_sessions = int(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        return {
            "attempts": attempts,
            "hint_usage": hints,
            "sessions": {"total": total_sessions, "mastery_stages": stages},
            "agent_runs": run_status,
        }

    def _event(
        self,
        db: sqlite3.Connection,
        session_id: str,
        event_type: str,
        payload: dict,
        idempotency_key: str | None,
    ) -> int:
        """Insert a session event. Returns the insert rowcount: 0 means an
        event with this idempotency key already exists (OR IGNORE swallowed
        the row) — callers enforcing replay protection must check it."""
        cursor = db.execute(
            "INSERT OR IGNORE INTO session_events(session_id,event_type,payload,created_at,idempotency_key) VALUES (?,?,?,?,?)",
            (session_id, event_type, self._json(payload), time.time(), idempotency_key),
        )
        return cursor.rowcount

    def _event_for_controller(
        self, session_id: str, event_type: str, payload: dict, idempotency_key: str | None
    ) -> None:
        with self._connect() as db:
            self._event(db, session_id, event_type, payload, idempotency_key)
