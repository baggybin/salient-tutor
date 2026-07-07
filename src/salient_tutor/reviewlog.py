"""Append-only review-event log — the scheduling telemetry substrate.

Every graded retrieval review appends one JSON line here, capturing the FULL
before/after state of the scheduler decision (grade, mastery before/after,
prior + new interval, when it was due, when it was actually reviewed). Unlike
the KG learner fact — which the scheduler *overwrites* in place on each review
(`kg.record_learner_review` is an upsert) — this log never forgets, so it is
the only place the tutor's spacing history survives.

Why a file, not the KG: a review event is audit history, not a graph fact or
recall material. Keeping it out of the KG avoids polluting semantic recall (no
`_META_PREFIXES` carve-out needed) and keeps the whole concern inside
salient-tutor. It is deliberately additive and load-bearing for nothing at
runtime — a bad write is swallowed (telemetry must never break a review).

This is Phase 0 of the scheduler work: measure before tuning. It makes
curve-improvement (SM-2 constants) evaluable against real retention, and — if
FSRS is ever opened — it is the review history FSRS needs to pretrain, which
the KG's overwrite-in-place model cannot provide.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("salient.tutor.reviewlog")

# Fields captured per event, in a stable order. `ts` is the review time;
# `review_due` is when the item was *scheduled* to resurface — the gap between
# a past `review_due` and this `ts` is the raw signal for whether spacing lands.
_FIELDS = (
    "ts",
    "topic",
    "grade",
    "mastery_before",
    "mastery_after",
    "prev_interval_days",
    "interval_days",
    "review_due",
    "predicate",
)


def log_path(work_root: str | Path) -> Path:
    """Canonical location of the append-only review log."""
    return Path(work_root) / "review_log.jsonl"


def append(work_root: str | Path, event: dict[str, Any]) -> None:
    """Append one review event as a JSON line. Best-effort: any failure is
    logged and swallowed — telemetry must never break the review it records."""
    try:
        path = log_path(work_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {k: event.get(k) for k in _FIELDS}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — telemetry is never load-bearing
        _log.exception("review-log append failed (ignored)")


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate telemetry over review events. The headline is ``recall_rate``:
    of the reviews where the item had a PRIOR schedule (``prev_interval_days``
    set — i.e. it came back around on a spacing gap), the fraction recalled
    (grade != 'again'). That is the direct signal for whether the scheduler's
    gaps land — a low rate means gaps are too long (items forgotten by due
    time); a rate near 1.0 with long intervals is the healthy target. First-ever
    sightings (no prior schedule) are excluded from the rate but counted in
    ``total``. ``recall_rate`` is None until at least one due review exists."""
    grades = {"again": 0, "hard": 0, "good": 0, "easy": 0}
    topics: set[str] = set()
    due_total = 0
    due_recalled = 0
    for e in events:
        g = e.get("grade")
        if g in grades:
            grades[g] += 1
        t = e.get("topic")
        if isinstance(t, str):
            topics.add(t)
        if e.get("prev_interval_days") is not None:
            due_total += 1
            if g != "again":
                due_recalled += 1
    return {
        "total": len(events),
        "topics": len(topics),
        "grades": grades,
        "reviews_at_due": due_total,
        "recall_rate": (due_recalled / due_total) if due_total else None,
    }


def read(
    work_root: str | Path, *, topic: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Read events oldest→newest, optionally filtered to one `topic` and capped
    to the most recent `limit`. Skips unparseable lines rather than raising."""
    path = log_path(work_root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if topic is not None and row.get("topic") != topic:
                continue
            events.append(row)
    except OSError:
        return []
    if limit is not None and limit >= 0:
        events = events[-limit:]
    return events
