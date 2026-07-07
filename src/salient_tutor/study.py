"""Study projects — operator-uploaded documents turned into teachable material.

A "study project" lets the operator bring their own source material (a PDF, a
paper, a runbook) and have the `librarian` agent read it natively and
pre-structure it into a searchable + teachable form the tutor then teaches
from. This module is the deterministic, daemon-free store side (mirrors
`tutor_export.py`'s "thin write side" shape); the RPC orchestration lives in
`salient/daemon/_commands_study.py`.

Layout (cross-engagement — works with NO engagement loaded, like tutoring):

    work_root()/study/<project_id>/
        uploads/    <sha8>-<safe-filename>   raw operator uploads, verbatim
        extracted/  <sha8>.md                the librarian's teachable output
        archive/    study_<id>_compact_*.json  compaction recovery points

State is a versioned envelope in the context META-KV table (key
`study:<project_id>`), mirroring the swarm-registry `{"_v":N,...}` +
`normalize_*` pattern. Searchable content is KG facts under the `study:<id>:`
namespace (permanent — study material is durable, like learner facts); the
daemon's existing embedding backfill embeds them, so this module stays
embedder-free exactly as `kg.py` does.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

# config inlined — work_root passed by daemon
from salient_tutor.export import slugify

# Versioned-envelope schema for the META-KV state blob. Bump when the shape
# changes; normalize_study tolerates older/legacy blobs.
STUDY_SCHEMA_VERSION = 1

# On-disk ceiling for one uploaded document. Documents (esp. image-heavy PDFs)
# routinely exceed the old 16 MB; this is the FINAL-size policy cap, decoupled
# from the socket line cap because large uploads are CHUNKED over the wire
# (study_upload reassembles), so a single RPC line never approaches it.
STUDY_UPLOAD_MAX_BYTES = 100 * 1024 * 1024

# Valid per-document lifecycle states (envelope `docs[].status`). `ocr` is the
# in-progress state while the optional OCR pre-pass adds a text layer to a
# scanned/image-only PDF before the librarian reads it.
DOC_STATUSES = ("uploaded", "ocr", "extracting", "extracted", "failed")


# ── on-disk layout ────────────────────────────────────────────────────────


def study_root() -> Path:
    """`<work_root>/study/` — created on demand, gitignored."""
    import os

    root = Path(os.environ.get("SALIENT_TUTOR_WORK_ROOT", Path.cwd() / "work"))
    d = root / "study"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_dir(project_id: str) -> Path:
    return study_root() / project_id


def uploads_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def extracted_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "extracted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def archive_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "archive"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── KG namespace helpers (single source of truth for the triple scheme) ─────


def namespace(project_id: str) -> str:
    return f"study:{project_id}:"


def doc_subject(project_id: str, sha: str) -> str:
    return f"{namespace(project_id)}doc:{sha[:8]}"


def chunk_subject(project_id: str, sha: str, index: int) -> str:
    return f"{namespace(project_id)}chunk:{sha[:8]}-{index}"


def sec_subject(project_id: str, sec_id: str) -> str:
    return f"{namespace(project_id)}sec:{sec_id}"


# ── project ids + state envelope ────────────────────────────────────────────


def meta_key(project_id: str) -> str:
    return f"study:{project_id}"


def new_project_id(title: str, existing: set[str]) -> str:
    """A filesystem-safe, unique project id from `title`. Appends `-2`, `-3`…
    only on collision with an id already in `existing`."""
    base = slugify(title)
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def _safe_name(filename: str) -> str:
    """Strip any path component and reduce to a filesystem-safe basename. The
    client-supplied name is NEVER used as a path — only as a display-ish
    suffix on the sha-prefixed stored name (no traversal possible)."""
    base = Path(filename or "").name  # drops dirs + leading separators
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return safe[:80] or "document"


def normalize_study(data: Any) -> dict[str, Any] | None:
    """Validate a decoded study blob into the canonical envelope-inner dict
    ``{project_id, title, created, updated, docs:[...], position:{...}}``.
    Garbage is dropped, never raised — callers wrap only the surrounding
    json.loads in try/except. Returns None if there's no usable project_id.

    Accepts both the versioned envelope (``{"_v":N,"study":{...}}``) and a
    legacy bare dict, mirroring normalize_swarms.
    """
    if isinstance(data, dict) and "_v" in data and isinstance(data.get("study"), dict):
        study = data["study"]
    else:
        study = data
    if not isinstance(study, dict):
        return None
    pid = study.get("project_id")
    if not isinstance(pid, str) or not pid.strip():
        return None

    clean_docs: list[dict[str, Any]] = []
    for d in study.get("docs") or []:
        if not isinstance(d, dict):
            continue
        sha = d.get("sha")
        filename = d.get("filename")
        if not isinstance(sha, str) or not isinstance(filename, str):
            continue
        status = d.get("status")
        if status not in DOC_STATUSES:
            status = "uploaded"
        try:
            chunk_count = int(d.get("chunk_count") or 0)
        except (TypeError, ValueError):
            chunk_count = 0
        clean_docs.append(
            {
                "filename": filename,
                "stored_name": str(d.get("stored_name") or ""),
                "sha": sha,
                "bytes": int(d.get("bytes") or 0) if str(d.get("bytes") or "").isdigit() else 0,
                "status": status,
                "chunk_count": chunk_count,
                "error": d.get("error") if isinstance(d.get("error"), str) else None,
                "ocr": bool(d.get("ocr")),
                "extracted_path": str(d.get("extracted_path") or "") or None,
            }
        )

    position = study.get("position")
    if not isinstance(position, dict):
        position = {}

    return {
        "project_id": pid,
        "title": str(study.get("title") or pid),
        "subject": _coerce_subject(study.get("subject")),
        "created": float(study.get("created") or 0.0) if _is_num(study.get("created")) else 0.0,
        "updated": float(study.get("updated") or 0.0) if _is_num(study.get("updated")) else 0.0,
        "docs": clean_docs,
        "position": position,
    }


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def new_study(
    project_id: str,
    title: str,
    *,
    subject: str = "cyber",
    now: float | None = None,
) -> dict[str, Any]:
    now = now if now is not None else time.time()
    return {
        "project_id": project_id,
        "title": title or project_id,
        "subject": _coerce_subject(subject),
        "created": now,
        "updated": now,
        "docs": [],
        "position": {},
    }


def _coerce_subject(value: Any) -> str:
    """Normalize a subject value to one of the valid subjects (cyber/biology/
    other), defaulting to cyber. Imported lazily to avoid a circular import
    (providers imports nothing from study, but keep the seam clean)."""
    from salient_tutor.providers import SUBJECTS

    s = str(value or "").strip().lower()
    return s if s in SUBJECTS else "cyber"


def envelope(study: dict[str, Any]) -> dict[str, Any]:
    """Wrap an inner study dict in the versioned envelope for persistence."""
    return {"_v": STUDY_SCHEMA_VERSION, "study": study}


def find_doc(study: dict[str, Any], sha: str) -> dict[str, Any] | None:
    for d in study.get("docs") or []:
        if d.get("sha") == sha:
            return d
    return None


# ── persistence over a context META-KV (duck-typed: meta_get/set/keys) ──────


def load_study(context: Any, project_id: str) -> dict[str, Any] | None:
    """Load + normalize the project envelope from the context META-KV, or None
    if absent/corrupt. Only json.loads is wrapped — normalize_study never
    raises."""
    raw = context.meta_get(meta_key(project_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return normalize_study(data)


def save_study(context: Any, study: dict[str, Any], *, now: float | None = None) -> None:
    """Stamp `updated` and persist the versioned envelope to the META-KV."""
    study = dict(study)
    study["updated"] = now if now is not None else time.time()
    context.meta_set(meta_key(study["project_id"]), json.dumps(envelope(study)))


def list_studies(context: Any) -> list[dict[str, Any]]:
    """Every project envelope in the META-KV (key `study:<project_id>`), newest
    first. Skips malformed blobs and any deeper `study:<id>:…` key defensively
    (project ids are colon-free slugs, so a top-level envelope has exactly one
    colon)."""
    out: list[dict[str, Any]] = []
    for k in context.meta_keys("study:"):
        pid = k[len("study:") :]
        if ":" in pid or not pid:
            continue
        raw = context.meta_get(k)
        if not raw:
            continue
        try:
            s = normalize_study(json.loads(raw))
        except (ValueError, TypeError):
            s = None
        if s:
            out.append(s)
    out.sort(key=lambda s: s.get("updated") or 0.0, reverse=True)
    return out


# ── uploads ─────────────────────────────────────────────────────────────────


def save_upload(project_id: str, client_filename: str, data: bytes) -> dict[str, Any]:
    """Write raw uploaded bytes under `uploads/` and return a doc descriptor.
    The stored filename is server-derived (`<sha8>-<safe>`) so a malicious
    client path can't escape the dir. Raises ValueError above the size cap.
    Dedupe is the caller's job (sha is the key)."""
    if len(data) > STUDY_UPLOAD_MAX_BYTES:
        raise ValueError(f"document too large ({len(data)} bytes > {STUDY_UPLOAD_MAX_BYTES})")
    if not data:
        raise ValueError("empty document")
    sha = hashlib.sha256(data).hexdigest()
    safe = _safe_name(client_filename)
    stored_name = f"{sha[:8]}-{safe}"
    path = uploads_dir(project_id) / stored_name
    path.write_bytes(data)
    return {
        "filename": Path(client_filename or safe).name or safe,
        "stored_name": stored_name,
        "sha": sha,
        "bytes": len(data),
        "status": "uploaded",
        "chunk_count": 0,
        "error": None,
        "ocr": False,
        "extracted_path": None,
    }


# ── OCR pre-pass (optional; for scanned / image-only PDFs) ───────────────────
# Adds a real text layer so a text-only or local librarian can ingest a scanned
# PDF (a vision model like minimax already reads page-images directly). Pure
# subprocess shell-outs with shutil.which presence checks — they NEVER raise; a
# missing binary degrades to a sentinel the caller turns into an actionable
# message. CPU-only (tesseract via ocrmypdf): no GPU / VRAM cost.


def ocr_path(project_id: str, stored_name: str) -> Path:
    """Sibling text-layered copy of an uploaded PDF: `<stored_name>.ocr.pdf` in
    the same uploads/ dir, so it stays inside the librarian's read-root."""
    return uploads_dir(project_id) / f"{stored_name}.ocr.pdf"


def has_text_layer(path: Path, *, sample_pages: int = 5) -> bool:
    """Whether `path` (a PDF) has an extractable text layer.

    Shells out to poppler ``pdftotext`` over the first `sample_pages` pages and
    treats empty/whitespace output as image-only (→ False). Conservatively
    returns True when we CAN'T tell — non-PDF, or ``pdftotext`` not installed —
    so we never misfire OCR or block a doc we can't probe (the librarian then
    reads it exactly as before)."""
    if Path(path).suffix.lower() != ".pdf":
        return True
    if shutil.which("pdftotext") is None:
        return True
    try:
        out = subprocess.run(
            ["pdftotext", "-l", str(sample_pages), str(path), "-"],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if out.returncode != 0:
        # pdftotext couldn't parse it (corrupt / not really a PDF) — we can't
        # tell, so assume text and let the librarian try (don't misfire OCR).
        return True
    return bool(out.stdout.strip())


def ocr_pdf(src: Path, dst: Path, *, timeout: int = 1800, lang: str = "eng") -> Path | None:
    """OCR a scanned PDF, writing a text-layered copy to `dst`; return `dst` on
    success or **None** when OCR is unavailable / failed (the caller surfaces an
    actionable message — never raised). Uses ``ocrmypdf --skip-text`` so any
    already-text pages pass through untouched. CPU-bound and slow on big docs —
    invoke via ``asyncio.to_thread``."""
    if shutil.which("ocrmypdf") is None:
        return None
    try:
        r = subprocess.run(
            [
                "ocrmypdf",
                "--skip-text",
                "--rotate-pages",
                "--deskew",
                "--output-type",
                "pdf",
                "-l",
                lang,
                str(src),
                str(dst),
            ],
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not Path(dst).exists():
        return None
    return Path(dst)


def text_path(project_id: str, sha8: str) -> Path:
    """Where the pre-extracted plain text for one document lives:
    ``extracted/<sha8>.txt`` (sibling to the librarian's ``<sha8>.md``). Kept
    inside the librarian's read-root so it can Read it natively."""
    return extracted_dir(project_id) / f"{sha8}.txt"


def _pdf_to_text(pdf: Path, *, first_pages: int | None = None) -> str | None:
    """Run ``pdftotext`` over `pdf`, returning the extracted text (or None on any
    failure / missing binary). `first_pages` caps extraction at the first N pages
    (None = whole doc). Pure subprocess; never raises."""
    if shutil.which("pdftotext") is None:
        return None
    cmd = ["pdftotext"]
    if first_pages is not None:
        cmd += ["-l", str(first_pages)]
    cmd += [str(pdf), "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    text = out.stdout.decode("utf-8", errors="replace")
    return text if text.strip() else None


def extract_text(
    project_id: str,
    doc_path: Path,
    sha8: str,
    *,
    first_pages: int | None = None,
) -> tuple[Path | None, str | None]:
    """Deterministically extract a document to plain text so ANY librarian model
    (text-only local models like Gemma/Llama/Qwen — which reject the page IMAGES
    the SDK's Read tool would otherwise render — as well as vision-capable ones)
    can ingest it as text.

    Writes ``extracted/<sha8>.txt`` and returns ``(path, error)``: ``(path, None)``
    on success, ``(None, error)`` when no text could be extracted. For PDFs with a
    text layer this is a fast ``pdftotext`` pass; scanned/image-only PDFs fall
    back to ``ocr_pdf`` (ocrmypdf → tesseract) then ``pdftotext`` again. Non-PDF
    files (.txt/.md) are copied verbatim. Never raises — a failure becomes an
    actionable error string the caller surfaces, and the librarian then falls
    back to reading the original file directly.

    `first_pages` caps a PDF at the first N pages (None = whole doc) — mirrors
    the prior "pages 1–20" librarian instruction for very large PDFs."""
    out = text_path(project_id, sha8)
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = Path(doc_path).suffix.lower()

    # Non-PDF: copy verbatim (.txt/.md/.markdown are already text).
    if suffix != ".pdf":
        try:
            out.write_bytes(Path(doc_path).read_bytes())
            return (out, None)
        except OSError as e:
            return (None, f"could not read {doc_path.name}: {e}")

    # PDF with a text layer: one fast pdftotext pass.
    if has_text_layer(doc_path):
        text = _pdf_to_text(doc_path, first_pages=first_pages)
        if text is not None:
            out.write_text(text, encoding="utf-8")
            return (out, None)

    # Scanned / image-only PDF: OCR a text-layered copy, then extract.
    ocr_dst = ocr_path(project_id, Path(doc_path).name)
    if ocr_pdf(doc_path, ocr_dst) is not None:
        text = _pdf_to_text(ocr_dst, first_pages=first_pages)
        if text is not None:
            out.write_text(text, encoding="utf-8")
            return (out, None)

    return (
        None,
        "could not extract text from this PDF (no text layer and OCR unavailable "
        "or failed) — install poppler/ocrmypdf, or use a vision-capable librarian model",
    )


# ── chunking (deterministic, heading/paragraph aware) ───────────────────────


def chunk_text(text: str, *, target_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split extracted text into overlapping, roughly `target_chars`-sized
    chunks for embedding. Deterministic and pure (unit-testable). Splits on
    paragraph boundaries first, packing whole paragraphs up to the target; a
    single paragraph longer than the target is hard-split with `overlap`-char
    carryover so a concept that straddles the cut is still recoverable on
    either side. Whitespace-only input → []."""
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
            # Flush the buffer, then hard-split the oversized paragraph.
            if buf:
                chunks.append(buf)
                buf = ""
            start = 0
            while start < len(para):
                chunks.append(para[start : start + target])
                if start + target >= len(para):
                    break
                start += target - ov
            continue
        if not buf:
            buf = para
        elif len(buf) + 2 + len(para) <= target:
            buf = f"{buf}\n\n{para}"
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


# ── KG ingest (embedder-free — the daemon backfill embeds these) ────────────


def embed_into_kg(
    kg: Any,
    *,
    project_id: str,
    doc_sha: str,
    doc_filename: str,
    chunks: list[str],
    agent: str = "librarian",
    page_ranges: list[str] | None = None,
) -> int:
    """Assert the searchable chunk facts for one document into the KG under the
    `study:<id>:` namespace. Each chunk becomes a permanent `passage` fact plus
    a `from_doc` edge back to the doc node. Returns the chunk count. Writes NO
    embeddings (kg.py stays embedder-free; the daemon's backfill embeds the new
    `passage` facts on its next pass).

    `page_ranges`, when given, is index-aligned to `chunks`: entry `i` is the
    source page range (e.g. ``"12-31"``) of chunk `i`, asserted as a `page_range`
    fact so the tutor can cite where a passage came from. Optional — callers that
    don't track pagination simply omit it."""
    ds = doc_subject(project_id, doc_sha)
    kg.assert_fact(ds, "filename", doc_filename, agent=agent, expires_at=None)
    n = 0
    for i, chunk in enumerate(chunks):
        body = (chunk or "").strip()
        if not body:
            continue
        cs = chunk_subject(project_id, doc_sha, i)
        # Self-describing object so semantic hits carry provenance inline
        # (str(Fact) is all the tutor sees from kg_semantic_query).
        kg.assert_fact(cs, "passage", f"{doc_filename}: {body}", agent=agent, expires_at=None)
        kg.assert_fact(cs, "from_doc", ds, agent=agent, expires_at=None)
        if page_ranges is not None and i < len(page_ranges) and page_ranges[i]:
            kg.assert_fact(cs, "page_range", page_ranges[i], agent=agent, expires_at=None)
        n += 1
    return n


def ingest_sections(
    kg: Any,
    *,
    project_id: str,
    sections: Any,
    agent: str = "librarian",
) -> int:
    """Write the librarian's STRUCTURED teaching scaffold into the KG under
    `study:<id>:sec:<sec-id>` (title/summary/objective/key_fact/drill/
    diagram_hint/prereq). These are pulled by exact kg_query (not semantic
    search) so the tutor can teach a section deterministically. Returns the
    number of sections ingested. Tolerant of a loosely-shaped LLM payload."""
    if not isinstance(sections, list):
        return 0
    n = 0
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            continue
        sid = str(sec.get("id") or "").strip() or str(i + 1)
        ss = sec_subject(project_id, sid)
        for key, pred in (
            ("title", "title"),
            ("summary", "summary"),
            ("objective", "objective"),
            ("diagram_hint", "diagram_hint"),
            ("prereq", "prereq"),
            ("page_range", "page_range"),
        ):
            v = sec.get(key)
            if isinstance(v, str) and v.strip():
                kg.assert_fact(ss, pred, v.strip(), agent=agent, expires_at=None)
        for kf in sec.get("key_facts") or []:
            if isinstance(kf, str) and kf.strip():
                kg.assert_fact(ss, "key_fact", kf.strip(), agent=agent, expires_at=None)
        for dr in sec.get("drills") or []:
            if isinstance(dr, dict):
                front = str(dr.get("front") or "").strip()
                back = str(dr.get("back") or "").strip()
                if front and back:
                    kg.assert_fact(ss, "drill", f"{front}::{back}", agent=agent, expires_at=None)
        n += 1
    return n


def first_section_id(parsed: dict[str, Any]) -> str | None:
    """The id of the first section in a parsed extraction, for the resume
    position pointer. None if there are no sections."""
    for i, sec in enumerate(parsed.get("sections") or []):
        if isinstance(sec, dict):
            return str(sec.get("id") or "").strip() or str(i + 1)
    return None
