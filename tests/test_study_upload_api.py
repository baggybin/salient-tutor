"""The daemon.study_upload ↔ study.save_upload seam + the /upload endpoint.

Regression for the interface drift where study_upload expected save_upload to
return {"doc": …} while save_upload returns the flat doc descriptor — every
upload 500'd (KeyError: 'doc') and the study/KG pipeline was dead on arrival.
"""

from __future__ import annotations

import asyncio
import base64

from fastapi.testclient import TestClient

from salient_tutor import web
from salient_tutor.daemon import TutorDaemon
from salient_tutor.study import load_study, new_study, save_study


class _FakeContext:
    """Duck-typed META-KV (meta_get/set/keys) — what study.py persistence needs."""

    def __init__(self):
        self.kv: dict[str, str] = {}

    def meta_get(self, key):
        return self.kv.get(key)

    def meta_set(self, key, value):
        self.kv[key] = value

    def meta_delete(self, key):
        self.kv.pop(key, None)

    def meta_keys(self, prefix=""):
        return [k for k in self.kv if k.startswith(prefix)]


class _DaemonShell:
    """Bare object carrying just what study_upload touches, bound to the real method."""

    study_upload = TutorDaemon.study_upload

    def __init__(self):
        self.context = _FakeContext()


def _shell_with_project(tmp_path, monkeypatch, pid="p1"):
    monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
    shell = _DaemonShell()
    save_study(shell.context, new_study(pid, "Test project"))
    return shell


class TestStudyUploadSeam:
    def test_upload_roundtrip(self, tmp_path, monkeypatch):
        shell = _shell_with_project(tmp_path, monkeypatch)
        res = shell.study_upload("p1", "notes.md", b"# Kerberos\n\nThe KDC issues tickets.\n")
        assert res["status"] == "uploaded"
        doc = res["doc"]
        assert doc["sha"] and doc["stored_name"].startswith(doc["sha"][:8])
        # descriptor recorded in the envelope; the stored file exists on disk
        study = load_study(shell.context, "p1")
        assert [d["sha"] for d in study["docs"]] == [doc["sha"]]
        stored = tmp_path / "study" / "p1" / "uploads" / doc["stored_name"]
        assert stored.read_bytes().startswith(b"# Kerberos")

    def test_upload_dedupes_by_sha(self, tmp_path, monkeypatch):
        shell = _shell_with_project(tmp_path, monkeypatch)
        shell.study_upload("p1", "notes.md", b"same bytes")
        shell.study_upload("p1", "renamed.md", b"same bytes")
        assert len(load_study(shell.context, "p1")["docs"]) == 1

    def test_unknown_project(self, tmp_path, monkeypatch):
        shell = _shell_with_project(tmp_path, monkeypatch)
        assert "error" in shell.study_upload("nope", "a.md", b"x")

    def test_empty_document_is_an_error_not_a_500(self, tmp_path, monkeypatch):
        shell = _shell_with_project(tmp_path, monkeypatch)
        res = shell.study_upload("p1", "a.md", b"")
        assert "empty" in res["error"]


class TestParseJsonReply:
    """Fence-tolerant JSON unwrap — the librarian wraps payloads in ```json."""

    def test_strict_json(self):
        from salient_tutor.daemon import _parse_json_reply

        assert _parse_json_reply('{"a": 1}') == {"a": 1}

    def test_fenced_with_language_tag(self):
        from salient_tutor.daemon import _parse_json_reply

        assert _parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}

    def test_bare_fence(self):
        from salient_tutor.daemon import _parse_json_reply

        assert _parse_json_reply('```\n{"a": 1}\n```') == {"a": 1}

    def test_surrounding_prose(self):
        from salient_tutor.daemon import _parse_json_reply

        assert _parse_json_reply('Here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}

    def test_no_json_raises(self):
        import pytest

        from salient_tutor.daemon import _parse_json_reply

        with pytest.raises(ValueError):
            _parse_json_reply("sorry, I can't do that")

    def test_raw_control_chars_in_string_values(self):
        """Local models emit raw tabs/newlines inside JSON strings instead of
        escaping them — "Invalid control character at: line N column M". The
        parser must tolerate this (strict=False), not fail extraction."""
        from salient_tutor.daemon import _parse_json_reply

        # A literal tab + literal newline inside a string value (not \t / \n).
        raw = '{"summary": "line one\nstill going\there", "status": "extracted"}'
        out = _parse_json_reply(raw)
        assert out["status"] == "extracted"
        assert "line one" in out["summary"]

    def test_control_chars_inside_fenced_block(self):
        from salient_tutor.daemon import _parse_json_reply

        raw = '```json\n{"chunks": ["a\tb", "c\nd"]}\n```'
        out = _parse_json_reply(raw)
        assert out["chunks"] == ["a\tb", "c\nd"]

    def test_missing_comma_repaired(self):
        """Long librarian extractions come back with dropped delimiters —
        "Expecting ',' delimiter: line 84 column 4". Structurally recoverable,
        so the repair fallback must save the upload instead of failing it."""
        from salient_tutor.daemon import _parse_json_reply

        raw = '{"status": "extracted", "chunks": ["a", "b"] "sections": [{"t": "x"}]}'
        out = _parse_json_reply(raw)
        assert out["status"] == "extracted"
        assert out["sections"] == [{"t": "x"}]

    def test_truncated_reply_repaired(self):
        """Output-cap truncation mid-array: repair closes the open structures."""
        from salient_tutor.daemon import _parse_json_reply

        raw = '{"status": "extracted", "chunks": ["alpha", "bet'
        out = _parse_json_reply(raw)
        assert out["status"] == "extracted"
        assert out["chunks"][0] == "alpha"

    def test_repair_garbage_still_raises(self):
        """The fallback only trusts a dict/list repair — prose stays an error."""
        import pytest

        from salient_tutor.daemon import _parse_json_reply

        with pytest.raises(ValueError):
            _parse_json_reply("{ this is not json at all }")

    def test_stray_bracket_in_prose_does_not_corrupt_slice(self):
        """A stray '[' in LEADING prose used to steal the slice start (the old
        min(find('{'), find('['))) and corrupt the JSON, failing at char 0 with
        "Expecting ',' delimiter: line 1 column 3 (char 2)". The span must now
        prefer the brace pair."""
        from salient_tutor.daemon import _parse_json_reply

        raw = 'Document [1] extracted:\n```json\n{"status": "extracted", "x": 1}\n```'
        out = _parse_json_reply(raw)
        assert out == {"status": "extracted", "x": 1}

    def test_parse_failure_error_includes_snippet(self):
        """When parsing fails outright, the surfaced error must include a
        snippet of the unparsed payload — otherwise the operator only sees the
        opaque CPython message and can't tell what the model returned."""
        import pytest

        from salient_tutor.daemon import _parse_json_reply

        raw = "{ definitely not json }"
        with pytest.raises(ValueError) as exc_info:
            _parse_json_reply(raw)
        assert "definitely not json" in str(exc_info.value)


class TestStudyExtractSeam:
    """study_extract end-to-end with a stubbed librarian returning fenced JSON."""

    def _extract_shell(self, tmp_path, monkeypatch, reply):
        shell = _shell_with_project(tmp_path, monkeypatch)
        shell.study_extract = TutorDaemon.study_extract.__get__(shell)
        shell.kg = None  # embed/ingest stubbed below

        async def fake_prompt(agent, message, **kw):
            assert agent == "librarian"
            return reply

        shell.prompt = fake_prompt
        calls = {}
        monkeypatch.setattr(
            "salient_tutor.study.embed_into_kg", lambda *a, **k: calls.setdefault("embed", k)
        )
        monkeypatch.setattr(
            "salient_tutor.study.ingest_sections", lambda *a, **k: calls.setdefault("ingest", k)
        )
        return shell, calls

    def test_fenced_reply_extracts(self, tmp_path, monkeypatch):
        reply = (
            '```json\n{"status": "extracted", "sections": [{"id": "1"}], "chunks": ["text"]}\n```'
        )
        shell, calls = self._extract_shell(tmp_path, monkeypatch, reply)
        up = shell.study_upload("p1", "notes.md", b"# hi\n")
        res = asyncio.run(shell.study_extract("p1", doc_sha=up["doc"]["sha"][:8]))
        assert res == {"status": "extracted", "sections": 1}
        assert "embed" in calls and "ingest" in calls
        # doc status flipped to extracted in the envelope
        assert load_study(shell.context, "p1")["docs"][0]["status"] == "extracted"

    def test_non_json_reply_fails_gracefully(self, tmp_path, monkeypatch):
        shell, _ = self._extract_shell(tmp_path, monkeypatch, "I could not read the file.")
        up = shell.study_upload("p1", "notes.md", b"# hi\n")
        res = asyncio.run(shell.study_extract("p1", doc_sha=up["doc"]["sha"][:8]))
        assert res["status"] == "failed" and "error" in res


class TestUploadEndpoint:
    def test_endpoint_decodes_and_uploads(self, tmp_path, monkeypatch):
        shell = _shell_with_project(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        b64 = base64.b64encode(b"# hi\n").decode()
        resp = TestClient(web.app).post(
            "/api/study/p1/upload", json={"filename": "hi.md", "data": b64}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "uploaded"

    def test_endpoint_surfaces_upload_errors_as_json(self, tmp_path, monkeypatch):
        shell = _shell_with_project(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        resp = TestClient(web.app).post(
            "/api/study/p1/upload", json={"filename": "hi.md", "data": ""}
        )
        assert resp.status_code == 200
        assert "empty" in resp.json()["error"]


class _RealKGShell:
    """Daemon shell bound to a real KnowledgeGraph + the study_* methods, so
    fact counts, purges, and on-disk delete are exercised against the real
    store. Mirrors _DaemonShell but adds kg + the new delete methods."""

    study_upload = TutorDaemon.study_upload
    study_list = TutorDaemon.study_list
    study_delete = TutorDaemon.study_delete
    study_delete_doc = TutorDaemon.study_delete_doc

    def __init__(self, tmp_path):
        import os

        from salient_core import KnowledgeGraph

        os.environ["SALIENT_TUTOR_WORK_ROOT"] = str(tmp_path)
        self.context = _FakeContext()
        self.kg = KnowledgeGraph(tmp_path / "kg.db")
        self.work_root = tmp_path


class TestStudyFactCountsAndDelete:
    """Per-project fact counts on /api/study/list + project & per-doc delete."""

    def _shell(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        shell = _RealKGShell(tmp_path)
        save_study(shell.context, new_study("p1", "Test project"))
        return shell

    def _seed_doc_facts(self, shell, pid, sha8, n_chunks=3):
        """Write a doc node + n passage chunks under study:{pid}: (the same
        scheme study.embed_into_kg uses), so counts + purges are meaningful."""
        from salient_tutor.study import chunk_subject, doc_subject

        shell.kg.assert_fact(doc_subject(pid, sha8), "filename", f"{sha8}.md", agent="test")
        for i in range(n_chunks):
            shell.kg.assert_fact(chunk_subject(pid, sha8, i), "passage", f"chunk {i}", agent="test")

    def test_list_endpoint_attaches_fact_counts(self, tmp_path, monkeypatch):
        shell = self._shell(tmp_path, monkeypatch)
        self._seed_doc_facts(shell, "p1", "abcdef12")  # 1 doc node + 3 chunks = 4 facts
        monkeypatch.setattr(web, "daemon", shell)
        resp = TestClient(web.app).get("/api/study/list")
        assert resp.status_code == 200
        p = resp.json()["projects"][0]
        assert p["project_id"] == "p1"
        assert p["facts"] == 4

    def test_per_doc_delete_purges_only_that_doc(self, tmp_path, monkeypatch):
        shell = self._shell(tmp_path, monkeypatch)
        # Two docs, each with a doc-node + 2 chunks.
        up_a = shell.study_upload("p1", "a.md", b"# A\ncontent A")
        up_b = shell.study_upload("p1", "b.md", b"# B\ncontent B")
        sha_a, sha_b = up_a["doc"]["sha"], up_b["doc"]["sha"]
        self._seed_doc_facts(shell, "p1", sha_a[:8], n_chunks=2)
        self._seed_doc_facts(shell, "p1", sha_b[:8], n_chunks=2)
        assert len(shell.kg.export_by_subject_prefix("study:p1:")) == 6  # 2 nodes + 4 chunks

        res = shell.study_delete_doc("p1", sha_a, confirm=True)
        assert res["status"] == "deleted" and res["sha"] == sha_a[:8]
        assert res["purged"] == 3  # doc-a node + its 2 chunks
        # Doc a is gone from the envelope; doc b + its facts survive.
        remaining = load_study(shell.context, "p1")["docs"]
        assert [d["sha"] for d in remaining] == [sha_b]
        facts = shell.kg.export_by_subject_prefix("study:p1:")
        assert len(facts) == 3
        assert all(sha_a[:8] not in f["subject"] for f in facts)

    def test_per_doc_delete_dry_run_is_safe(self, tmp_path, monkeypatch):
        shell = self._shell(tmp_path, monkeypatch)
        up = shell.study_upload("p1", "a.md", b"# A\ncontent A")
        sha = up["doc"]["sha"]
        self._seed_doc_facts(shell, "p1", sha[:8], n_chunks=1)
        res = shell.study_delete_doc("p1", sha, confirm=False)
        assert res["status"] == "dry_run"
        # Nothing was purged — doc still present.
        assert len(load_study(shell.context, "p1")["docs"]) == 1

    def test_project_delete_confirm_true_removes_facts_and_dir(self, tmp_path, monkeypatch):
        shell = self._shell(tmp_path, monkeypatch)
        shell.study_upload("p1", "a.md", b"# A\ncontent A")
        self._seed_doc_facts(shell, "p1", "abcdef12", n_chunks=2)
        assert len(shell.kg.export_by_subject_prefix("study:p1:")) == 3
        pdir = tmp_path / "study" / "p1"
        assert pdir.exists()

        res = shell.study_delete("p1", confirm=True)
        assert res == {"status": "deleted", "project_id": "p1"}
        assert shell.kg.export_by_subject_prefix("study:p1:") == []
        assert not pdir.exists()

    def test_per_doc_delete_endpoint(self, tmp_path, monkeypatch):
        shell = self._shell(tmp_path, monkeypatch)
        up = shell.study_upload("p1", "a.md", b"# A\ncontent A")
        sha = up["doc"]["sha"]
        self._seed_doc_facts(shell, "p1", sha[:8], n_chunks=1)
        monkeypatch.setattr(web, "daemon", shell)
        # TestClient.delete() doesn't accept json=; send the body explicitly.
        resp = TestClient(web.app).request(
            "DELETE",
            f"/api/study/p1/doc/{sha}",
            content='{"confirm": true}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert len(load_study(shell.context, "p1")["docs"]) == 0


class TestExtractText:
    """Deterministic text extraction so ANY librarian model (text-only local
    models that reject page IMAGES, as well as vision models) can ingest a doc."""

    def test_non_pdf_copied_verbatim(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        from salient_tutor import study as st

        src = tmp_path / "src"
        src.mkdir()
        f = src / "notes.md"
        f.write_text("# Heading\n\nbody text")
        out, err = st.extract_text("p1", f, "abcdef12")
        assert err is None and out is not None
        assert out.read_text() == "# Heading\n\nbody text"
        assert out.name == "abcdef12.txt"

    def test_pdf_with_text_layer_uses_pdftotext(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        from salient_tutor import study as st

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        monkeypatch.setattr(st, "has_text_layer", lambda p, **k: True)
        monkeypatch.setattr(st, "_pdf_to_text", lambda p, **k: "extracted page text")
        out, err = st.extract_text("p1", pdf, "12345678", first_pages=20)
        assert err is None and out is not None
        assert out.read_text() == "extracted page text"

    def test_scanned_pdf_falls_back_to_ocr(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        from salient_tutor import study as st

        pdf = tmp_path / "scan.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        # No text layer → first pdftotext returns nothing → OCR runs → second
        # pdftotext over the OCR'd copy succeeds.
        monkeypatch.setattr(st, "has_text_layer", lambda p, **k: False)
        calls = {"ocr": 0}

        def fake_ocr(src, dst, **k):
            calls["ocr"] += 1
            dst.write_bytes(b"%PDF ocr'd")
            return dst

        monkeypatch.setattr(st, "ocr_pdf", fake_ocr)
        monkeypatch.setattr(st, "_pdf_to_text", lambda p, **k: "ocr'd text")
        out, err = st.extract_text("p1", pdf, "abcd0000")
        assert err is None and out is not None
        assert out.read_text() == "ocr'd text"
        assert calls["ocr"] == 1

    def test_pdf_extraction_failure_returns_error_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        from salient_tutor import study as st

        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        monkeypatch.setattr(st, "has_text_layer", lambda p, **k: False)
        monkeypatch.setattr(st, "ocr_pdf", lambda src, dst, **k: None)  # OCR unavailable
        out, err = st.extract_text("p1", pdf, "dead0000")
        assert out is None
        assert "could not extract" in err


class TestStudyExtractTextPath:
    """study_extract pre-extracts text and INLINES it into the librarian prompt
    (not the PDF, and not a Read-the-.txt tool call), so a text-only model gets
    the text directly and small local models never mangle a Read path."""

    def _shell(self, tmp_path, monkeypatch, reply):
        shell = _shell_with_project(tmp_path, monkeypatch)
        shell.study_extract = TutorDaemon.study_extract.__get__(shell)
        shell.kg = None
        captured = {}

        async def fake_prompt(agent, message, **kw):
            captured["agent"] = agent
            captured["message"] = message
            return reply

        shell.prompt = fake_prompt
        monkeypatch.setattr("salient_tutor.study.embed_into_kg", lambda *a, **k: None)
        monkeypatch.setattr("salient_tutor.study.ingest_sections", lambda *a, **k: None)
        return shell, captured

    def test_librarian_pointed_at_text_file_for_pdf(self, tmp_path, monkeypatch):
        # A PDF with a text layer → the extracted text is inlined into the prompt,
        # never the .pdf path (so a text-only model gets text, not images, and no
        # Read tool-call can fail).
        reply = '```json\n{"status": "extracted", "sections": [], "chunks": ["x"]}\n```'
        shell, captured = self._shell(tmp_path, monkeypatch, reply)
        up = shell.study_upload("p1", "doc.pdf", b"%PDF-1.4 fake")
        monkeypatch.setattr("salient_tutor.study.has_text_layer", lambda p, **k: True)
        monkeypatch.setattr("salient_tutor.study._pdf_to_text", lambda p, **k: "the page text")
        res = asyncio.run(shell.study_extract("p1", doc_sha=up["doc"]["sha"][:8]))
        assert res == {"status": "extracted", "sections": 0}
        # The prompt inlines the extracted text and never names the .pdf.
        assert "the page text" in captured["message"]
        assert ".pdf" not in captured["message"]

    def test_non_pdf_uses_verbatim_text(self, tmp_path, monkeypatch):
        reply = '```json\n{"status": "extracted", "sections": [], "chunks": ["x"]}\n```'
        shell, captured = self._shell(tmp_path, monkeypatch, reply)
        up = shell.study_upload("p1", "notes.md", b"# hi\nbody")
        asyncio.run(shell.study_extract("p1", doc_sha=up["doc"]["sha"][:8]))
        # The .md's verbatim text is inlined into the prompt.
        assert "# hi\nbody" in captured["message"]


# ── /api/study/{id}/extract/stream — live librarian progress (SSE) ────────────


def test_extract_stream_relays_progress_then_done(monkeypatch):
    """The SSE stream surfaces the librarian's live events as `progress` lines
    and ends with a `done` carrying the same result dict as the blocking POST."""

    class _StreamStub:
        def __init__(self):
            self._q = asyncio.Queue()

        def subscribe_events(self):
            return self._q, []

        def unsubscribe_events(self, q):
            pass

        async def study_extract(self, project_id, doc_sha=None):
            await self._q.put({"agent": "librarian", "kind": "thinking", "text": ""})
            await asyncio.sleep(0.02)
            await self._q.put({"agent": "librarian", "kind": "tool-call", "text": "kg_write(x)"})
            await asyncio.sleep(0.02)
            # an event from another agent must NOT leak into the stream
            await self._q.put({"agent": "tutor", "kind": "thinking", "text": ""})
            await asyncio.sleep(0.02)
            return {"status": "extracted", "sections": 3}

    monkeypatch.setattr(web, "daemon", _StreamStub())
    r = TestClient(web.app).get("/api/study/p1/extract/stream?doc_sha=abc12345")
    assert r.status_code == 200
    body = r.text
    assert "extracting text from the document" in body  # initial progress
    assert "reading & structuring" in body  # relayed 'thinking'
    assert "kg_write" in body  # relayed 'tool-call'
    assert '"status": "extracted"' in body and '"sections": 3' in body  # terminal done


def test_extract_stream_daemon_not_started(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)
    r = TestClient(web.app).get("/api/study/p1/extract/stream")
    assert r.status_code == 200
    assert "daemon not started" in r.text
