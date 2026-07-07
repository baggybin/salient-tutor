"""Tests for the study-project store — uploads, envelope, KG namespace."""

from salient_tutor.study import (  # noqa: F401
    _safe_name,
    chunk_text,
    doc_subject,
    embed_into_kg,
    envelope,
    ingest_sections,
    meta_key,
    namespace,
    new_study,
    normalize_study,
    sec_subject,
)


class TestNamespaceScheme:
    """The study:<id>: KG namespace — pinned so the schema can't drift."""

    def test_namespace(self):
        assert namespace("abc123") == "study:abc123:"

    def test_doc_subject(self):
        assert doc_subject("proj1", "abcd1234") == "study:proj1:doc:abcd1234"

    def test_sec_subject(self):
        assert sec_subject("proj1", "1") == "study:proj1:sec:1"

    def test_meta_key(self):
        assert meta_key("proj1") == "study:proj1"


class TestSafeName:
    """Stored names are server-derived — no client path crosses a boundary."""

    def test_strips_dirs(self):
        assert "/" not in _safe_name("../../etc/passwd")
        assert ".." not in _safe_name("../../etc/passwd")

    def test_substitutes_bad_chars(self):
        result = _safe_name("file with spaces!@#.pdf")
        assert " " not in result
        assert all(c.isalnum() or c in "._-" for c in result)

    def test_caps_length(self):
        result = _safe_name("a" * 200 + ".pdf")
        assert len(result) <= 80


class TestNormalizeStudy:
    """The versioned envelope validator — drops garbage, never raises."""

    def test_valid_envelope(self):
        data = {"_v": 1, "study": {"project_id": "test", "title": "Test", "docs": []}}
        result = normalize_study(data)
        assert result is not None
        assert result["project_id"] == "test"

    def test_garbage_returns_none(self):
        assert normalize_study("garbage") is None
        assert normalize_study(None) is None
        assert normalize_study({}) is None

    def test_legacy_dict(self):
        """Bare dict without _v envelope should still normalize."""
        data = {"project_id": "test", "title": "Test", "docs": []}
        result = normalize_study(data)
        assert result is not None


class TestNewStudy:
    def test_creates_envelope(self):
        study = new_study("pid", "My Project")
        env = envelope(study)
        assert env["_v"] == 1
        assert env["study"]["project_id"] == "pid"
        assert env["study"]["title"] == "My Project"
        assert env["study"]["docs"] == []


class TestChunkText:
    def test_empty(self):
        assert chunk_text("") == []

    def test_single_para(self):
        assert chunk_text("Hello world.") == ["Hello world."]

    def test_multiple_paras(self):
        text = "\n\n".join(f"Paragraph {i}." for i in range(10))
        chunks = chunk_text(text)
        assert len(chunks) >= 1
        assert all(len(c) <= 1200 + 150 for c in chunks)


class TestEmbedIntoKG:
    """embed_into_kg writes chunks + sections into the study: namespace."""

    def test_embeds_parsed_content(self, tmp_path):
        from salient_core.memory.kg import KnowledgeGraph

        kg = KnowledgeGraph(tmp_path / "test.db")
        chunks = ["This is a passage about X.", "More content here."]
        embed_into_kg(
            kg,
            project_id="testproj",
            doc_sha="abcd1234",
            doc_filename="test.pdf",
            chunks=chunks,
        )
        sections = [
            {
                "id": "1",
                "title": "Intro",
                "objective": "Understand X",
                "key_facts": ["fact one"],
                "drills": [{"front": "What is X?", "back": "X is..."}],
                "diagram_hint": "flowchart LR A-->B",
                "prereq": "",
            }
        ]
        ingest_sections(kg, project_id="testproj", sections=sections)
        facts = kg.export_by_subject_prefix("study:testproj:")
        assert len(facts) > 0
        subjects = {f["subject"] for f in facts}
        assert any("sec:" in s for s in subjects)
        assert any("chunk:" in s for s in subjects)
