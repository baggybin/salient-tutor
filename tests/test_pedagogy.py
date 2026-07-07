"""Tests for the pedagogy KG ingestion — mnemonic techniques seeded into the KG."""

from pathlib import Path

import pytest
from salient_core.memory.kg import KnowledgeGraph

from salient_tutor.pedagogy import NAMESPACE, import_bundle, purge, subject_for

_BUNDLE = Path(__file__).resolve().parent.parent / "data" / "pedagogy_bundle.json"


@pytest.fixture
def kg(tmp_path):
    """Fresh KG for each test."""
    return KnowledgeGraph(tmp_path / "test_kg.db")


def _pedagogy_facts(kg):
    """Helper: all pedagogy: facts via prefix export."""
    return kg.export_by_subject_prefix("pedagogy:")


class TestBundleExists:
    def test_bundle_shipped(self):
        assert _BUNDLE.exists(), "pedagogy_bundle.json must ship in data/"
        assert _BUNDLE.stat().st_size > 1000, "bundle suspiciously small"


class TestSubjectFor:
    """The canonical pedagogy:<kind>:<tail> subject scheme."""

    def test_concept(self):
        assert (
            subject_for("concept_journey_method", "concept") == "pedagogy:technique:journey_method"
        )

    def test_rationale(self):
        assert subject_for("rationale_001", "rationale") == "pedagogy:rationale:001"

    def test_document(self):
        assert subject_for("doc_intro", "document") == "pedagogy:doc:doc_intro"

    def test_paper(self):
        result = subject_for("paper_001", "paper")
        assert result.startswith("pedagogy:paper:")


class TestImportBundle:
    """End-to-end: ingest the bundle, verify facts land in the KG."""

    def test_import_adds_facts(self, kg):
        stats = import_bundle(
            kg,
            bundle_path=_BUNDLE,
            source_root=_BUNDLE.parent,
            with_prose=False,
        )
        assert stats["facts"] > 0, "bundle should produce facts"
        assert stats["edges"] > 0, "bundle should produce edges"

    def test_import_is_idempotent(self, kg):
        """Second import max-merges, doesn't duplicate."""
        import_bundle(kg, bundle_path=_BUNDLE, source_root=_BUNDLE.parent, with_prose=False)
        facts1 = _pedagogy_facts(kg)
        import_bundle(kg, bundle_path=_BUNDLE, source_root=_BUNDLE.parent, with_prose=False)
        facts2 = _pedagogy_facts(kg)
        assert len(facts1) == len(facts2), "re-import should not duplicate facts"

    def test_import_seeds_techniques(self, kg):
        """The bundle should contain known memory techniques."""
        import_bundle(kg, bundle_path=_BUNDLE, source_root=_BUNDLE.parent, with_prose=False)
        facts = _pedagogy_facts(kg)
        joined = " ".join(str(f.get("object", "")).lower() for f in facts)
        assert any(kw in joined for kw in ["loci", "journey", "palace", "link", "peg"]), (
            "expected at least one known memory technique"
        )

    def test_import_seeds_rationales(self, kg):
        """The bundle should contain rationale nodes (the WHY behind techniques)."""
        import_bundle(kg, bundle_path=_BUNDLE, source_root=_BUNDLE.parent, with_prose=False)
        rationales = kg.export_by_subject_prefix("pedagogy:rationale:")
        assert len(rationales) > 0, "expected rationale facts"

    def test_purge_clears_namespace(self, kg):
        """purge() removes all pedagogy: facts."""
        import_bundle(kg, bundle_path=_BUNDLE, source_root=_BUNDLE.parent, with_prose=False)
        assert len(_pedagogy_facts(kg)) > 0
        purged = purge(kg)
        assert purged > 0
        assert len(_pedagogy_facts(kg)) == 0


class TestNamespace:
    def test_namespace_is_pedagogy(self):
        assert NAMESPACE == "pedagogy:"
