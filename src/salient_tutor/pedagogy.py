"""Ingest an external pedagogy/mnemonic knowledge graph into salient's KG.

A graphify-built bundle (``graphify-out/kg_bundle.json``) distils memory
techniques, the WHY behind them, and how they cluster — extracted from study /
memory books — into a PEDAGOGICAL meta-layer. This module pulls that graph plus
its line-addressed source prose into a permanent, global ``pedagogy:`` KG
namespace the tutor consults at teach time to choose HOW to encode a stubborn
fact. It is the how-to-TEACH sibling of ``study:`` (what the operator uploaded)
and ``learner:op`` (what the operator knows).

Design mirrors :mod:`salient.study`: pure-ish helpers + KG writes through
``kg.assert_fact`` only (no daemon, no clock beyond assert_fact's own ts), so
the two ingestion paths read the same way. Every fact is asserted under one
``agent="graphify"`` and ``expires_at=None`` (permanent), so re-imports
max-merge a single corroborator instead of inflating confidence, and the data
never expires out of the gradebook of teaching strategies.

Critically, pedagogy facts live under ``pedagogy:`` precisely so the KG's
default (unscoped) semantic search EXCLUDES them (see ``kg._META_PREFIXES``):
the tutor reaches them only via ``kg_semantic_query(subject_prefix="pedagogy:")``
or a one-hop ``kg_neighbors`` off a known ``pedagogy:`` node.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# chunk_text inlined (was from . import study)


def chunk_text(text: str, *, target_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split text into overlapping, roughly target_chars-sized chunks."""
    text = (text or "").strip()
    if not text:
        return []
    target = max(1, int(target_chars))
    ov = max(0, min(int(overlap), target - 1))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > target:
            if buf:
                chunks.append(buf)
                buf = ""
            start = 0
            while start < len(para):
                end = min(start + target, len(para))
                if end < len(para) and start > 0:
                    start = max(0, start - ov)
                chunks.append(para[start:end])
                start = end
        elif len(buf) + len(para) + 2 > target and buf:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


# ── KG namespace helpers (single source of truth for the triple scheme) ──────

NAMESPACE = "pedagogy:"
IMPORT_AGENT = "graphify"

# Bundle node-id prefixes → the pedagogy: subject kind. A node's file_type is
# the authority for its kind; the id prefix only supplies the readable tail.
_KIND_BY_FILE_TYPE = {
    "concept": "technique",  # entity_* concepts get re-kinded below
    "rationale": "rationale",
    "document": "doc",
    "paper": "paper",
}
# id-prefix → (kind, prefix-to-strip). Applied AFTER file_type so named people
# (entity_cicero, entity_tony_buzan) land under pedagogy:entity:, not technique:.
_KIND_BY_ID_PREFIX = (
    ("concept_", "technique"),
    ("rationale_", "rationale"),
    ("entity_", "entity"),
    ("extracted_", "doc"),
    ("he_", "family"),
)


def _kind_and_tail(node_id: str, file_type: str | None) -> tuple[str, str]:
    """Resolve a bundle node id + file_type to a (kind, tail) pair. file_type
    decides the kind for the common cases; the id prefix refines it (entities)
    and always supplies the human tail with its prefix stripped."""
    kind = _KIND_BY_FILE_TYPE.get(file_type or "", "node")
    tail = node_id
    for pfx, _pk in _KIND_BY_ID_PREFIX:
        if node_id.startswith(pfx):
            tail = node_id[len(pfx) :]
            # entity_* are people/works (file_type concept|paper) — keep them
            # out of the technique pool so traversal/strategy reads stay clean.
            if pfx == "entity_":
                kind = "paper" if file_type == "paper" else "entity"
            break
    return kind, tail


def subject_for(node_id: str, file_type: str | None) -> str:
    """Canonical ``pedagogy:<kind>:<tail>`` subject for a bundle node. The SAME
    function is used for node subjects AND edge endpoints, so asserted edges
    line up with asserted node subjects (kg_neighbors matches by exact string)."""
    kind, tail = _kind_and_tail(node_id, file_type)
    return f"{NAMESPACE}{kind}:{tail}"


def family_subject(hyperedge_id: str) -> str:
    tail = hyperedge_id[3:] if hyperedge_id.startswith("he_") else hyperedge_id
    return f"{NAMESPACE}family:{tail}"


def community_subject(community_id: Any) -> str:
    return f"{NAMESPACE}community:{community_id}"


def chunk_subject(node_subject: str, index: int) -> str:
    """A passage subject hung off a node subject (mirrors study chunk subjects).
    e.g. ``pedagogy:technique:journey_method`` → ``…:journey_method#0``."""
    return f"{node_subject}#{index}"


# ── source_location parsing + prose slicing ─────────────────────────────────

_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")
_SINGLE_RE = re.compile(r"^\d+$")


def parse_source_location(sl: str | None) -> list[tuple[int, int]]:
    """Parse a bundle ``source_location`` into 1-indexed inclusive line ranges.

    Handles every form present in real bundles: ``lines 64-123`` /
    ``lines 80-83, 824-826`` (comma multi-range) / ``lines ~2600-3000``
    (tilde-approximate) / ``lines 681, 1029-1047`` (mixed single + range) /
    singular ``line 206``. Unparseable parts are skipped, not fatal."""
    if not sl:
        return []
    body = sl.lower().replace("lines", "").replace("line", "").replace("~", "")
    out: list[tuple[int, int]] = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        m = _RANGE_RE.search(part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                out.append((a, b))
        elif _SINGLE_RE.match(part):
            n = int(part)
            out.append((n, n))
    return out


def slice_prose(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    """Join the given 1-indexed inclusive line ranges out of `lines` (a file's
    splitlines()). Ranges are clamped to the file; empties drop out."""
    parts: list[str] = []
    for a, b in ranges:
        a = max(1, a)
        b = min(len(lines), b)
        if a > b:
            continue
        chunk = "\n".join(lines[a - 1 : b]).strip()
        if chunk:
            parts.append(chunk)
    return "\n\n".join(parts).strip()


# ── the importer ────────────────────────────────────────────────────────────

# Node kinds whose source prose carries real technique CONTENT worth embedding.
# Documents (chapter-level, some tilde-approximate multi-hundred-line ranges)
# and entities/papers are structural-only in v1 — they get attribute + edge
# facts but no passage chunks (see the roadmap: doc-section prose is Tier 2).
_PROSE_KINDS = ("technique", "rationale")

# Verbatim edge relations → KG predicates (walkable by kg_neighbors).
_EDGE_RELATIONS = frozenset(
    {
        "conceptually_related_to",
        "references",
        "cites",
        "rationale_for",
        "semantically_similar_to",
    }
)


def import_bundle(
    kg: Any,
    *,
    bundle_path: str | Path,
    source_root: str | Path,
    agent: str = IMPORT_AGENT,
    with_prose: bool = True,
) -> dict[str, int]:
    """Ingest a graphify ``kg_bundle.json`` into the ``pedagogy:`` namespace.

    `bundle_path` is the kg_bundle.json; `source_root` is the directory the
    bundle's relative ``source_file`` paths resolve against (the graphify
    project root, e.g. the parent of ``graphify-out/``). All facts are permanent
    and attributed to one `agent` so re-imports dedupe-merge in place.

    Returns a counts dict: nodes / edges / families / communities / passages /
    facts. Idempotent: re-running over the same bundle updates rows, never
    duplicates (assert_fact dedupes on the exact triple)."""
    bundle_path = Path(bundle_path)
    source_root = Path(source_root)
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    hyperedges = data.get("hyperedges") or []
    communities = data.get("communities") or []

    counts = {"nodes": 0, "edges": 0, "families": 0, "communities": 0, "passages": 0, "facts": 0}

    def _assert(s: str, p: str, o: str) -> None:
        s, p, o = (s or "").strip(), (p or "").strip(), (o or "").strip()
        if not s or not p or not o:
            return  # guard: assert_fact raises on empty s/p/o
        kg.assert_fact(s, p, o, agent=agent, expires_at=None)
        counts["facts"] += 1

    # Canonical id → subject for EVERY node, so edge endpoints resolve to the
    # same subjects the node attribute facts use.
    id_to_subject: dict[str, str] = {}
    id_to_kind: dict[str, str] = {}
    for n in nodes:
        nid = n.get("id")
        if not nid:
            continue
        ft = n.get("file_type")
        kind, _ = _kind_and_tail(nid, ft)
        id_to_subject[nid] = subject_for(nid, ft)
        id_to_kind[nid] = kind

    # Community labels (taxonomy buckets). Some communities (Geography, History,
    # Language, Math, Revision, LTM/WM) carry no technique/rationale nodes —
    # they supply a label only; the tutor falls back to the prompt primitives.
    for c in communities:
        cid = c.get("id")
        if cid is None:
            continue
        label = (c.get("label") or "").strip()
        if label:
            _assert(community_subject(cid), "label", label)
            counts["communities"] += 1

    # Source-file line cache (read each .txt once).
    _file_lines: dict[str, list[str]] = {}

    def _lines_for(rel: str) -> list[str]:
        if rel not in _file_lines:
            p = source_root / rel
            try:
                _file_lines[rel] = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                _file_lines[rel] = []
        return _file_lines[rel]

    # Nodes: attribute facts + (for technique/rationale) sliced prose passages.
    for n in nodes:
        nid = n.get("id")
        if not nid:
            continue
        subj = id_to_subject[nid]
        kind = id_to_kind[nid]
        label = (n.get("label") or "").strip()
        for key in ("label", "file_type", "source_file", "source_location"):
            v = n.get(key)
            if isinstance(v, str) and v.strip():
                _assert(subj, key, v)
        comm = n.get("community")
        if comm is not None:
            # Derive community membership from the node's OWN attribute, not the
            # community.node_ids lists (which carry phantom ids absent from
            # nodes — those would assert dangling edges).
            _assert(subj, "in_community", community_subject(comm))
        counts["nodes"] += 1

        if with_prose and kind in _PROSE_KINDS:
            ranges = parse_source_location(n.get("source_location"))
            rel = n.get("source_file") or ""
            prose = slice_prose(_lines_for(rel), ranges) if (ranges and rel) else ""
            if prose:
                for i, body in enumerate(chunk_text(prose)):
                    cs = chunk_subject(subj, i)
                    # Self-describing object so a semantic hit carries the
                    # technique name inline (str(Fact) is all the tutor sees).
                    obj = f"{label}: {body}" if label else body
                    _assert(cs, "passage", obj)
                    _assert(cs, f"from_{kind}", subj)
                    sl = (n.get("source_location") or "").strip()
                    if sl:
                        _assert(cs, "source_location", sl)
                    counts["passages"] += 1

    # Hyperedges: pattern families + membership.
    for h in hyperedges:
        hid = h.get("id")
        if not hid:
            continue
        fsubj = family_subject(hid)
        label = (h.get("label") or "").strip()
        if label:
            _assert(fsubj, "label", label)
        for member_id in h.get("nodes") or []:
            msubj = id_to_subject.get(member_id)
            if msubj:
                _assert(msubj, "member_of_family", fsubj)
        counts["families"] += 1

    # Edges: verbatim relation → predicate, both endpoints via the canonical map.
    for e in edges:
        rel = e.get("relation")
        if rel not in _EDGE_RELATIONS:
            continue
        src = id_to_subject.get(e.get("source"))
        dst = id_to_subject.get(e.get("target"))
        if not src or not dst:
            continue  # endpoint not in nodes — skip rather than dangle
        _assert(src, rel, dst)
        counts["edges"] += 1

    return counts


def purge(kg: Any) -> int:
    """Remove every ``pedagogy:`` fact (idempotent teardown). Returns the count
    purged. Mirrors the study namespace teardown."""
    return kg.purge_by_subject_prefix(NAMESPACE)


# ── universal (engagement-independent) store ─────────────────────────────────


def global_store_path() -> Path:
    """Canonical, engagement-INDEPENDENT home of the ``pedagogy:`` namespace.

    The pedagogy meta-layer is global teaching knowledge, not per-engagement
    evidence — it belongs to the operator, not a target. `pedagogy_import` writes
    here, and every daemon seeds its live KG from here at boot (see `seed_into`),
    so the tutor's how-to-teach knowledge is present in EVERY engagement no
    matter how its KG was created. Overridable via ``SALIENT_PEDAGOGY_STORE``
    (tests isolate to a temp path)."""
    env = os.environ.get("SALIENT_PEDAGOGY_STORE")
    if env:
        return Path(env)
    return Path.home() / ".salient" / "pedagogy.kg.db"


def seed_into(kg: Any, *, source_path: str | Path | None = None) -> int:
    """Copy the ``pedagogy:`` namespace from the canonical global store into
    `kg`. Idempotent and cheap: a NO-OP when the store doesn't exist yet, or when
    `kg` already carries pedagogy facts (already seeded, or `kg` IS the store).
    Returns the number of facts seeded. Embeddings are NOT copied (they are
    per-DB / per-model); the engagement's own embeddings backfill vectorizes the
    seeded passages. Called at daemon boot — the mechanism that makes the
    meta-layer universal across engagements."""
    src = Path(source_path) if source_path is not None else global_store_path()
    if not src.exists():
        return 0
    if kg.query(subject=NAMESPACE, limit=1):
        return 0  # already present (seeded before, or kg is the store itself)
    from salient_core import KnowledgeGraph

    store = KnowledgeGraph(src)
    try:
        facts = store.export_by_subject_prefix(NAMESPACE)
    finally:
        store.close()
    n = 0
    for f in facts:
        s, p, o = f.get("subject"), f.get("predicate"), f.get("object")
        if not (s and p and o):
            continue
        try:
            kg.assert_fact(s, p, o, agent=f.get("agent") or IMPORT_AGENT, expires_at=None)
            n += 1
        except Exception:  # noqa: BLE001 — one bad row never blocks boot
            continue
    return n
