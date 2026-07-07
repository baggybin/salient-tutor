"""Substring tests for the tutor system prompt.

Every load-bearing string in prompts/tutor.md is pinned here. If a future
prompt-compression pass or careless edit destroys one, this test breaks before
the operator's experience does.
"""

from pathlib import Path

import pytest

PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "tutor.md").read_text()


class TestLessonLoopPhases:
    """The 9 phase names are load-bearing — they structure every lesson."""

    @pytest.mark.parametrize(
        "phase",
        [
            "DIAGNOSE",
            "OBJECTIVE",
            "MODEL",
            "CHECK",
            "ANCHOR",
            "DRILL",
            "REFLECT",
            "CARDS",
            "ELABORATE",
        ],
    )
    def test_phase_name_present(self, phase):
        assert phase in PROMPT, f"LESSON LOOP phase '{phase}' missing from prompt"


class TestPrimeDirectives:
    """The pedagogical invariants — drop any and the tutor drifts."""

    def test_retrieval_is_engine(self):
        assert "RETRIEVAL IS THE ENGINE" in PROMPT

    def test_dual_coding(self):
        assert "DUAL CODING ALWAYS" in PROMPT

    def test_unicorn_rule(self):
        assert "THE UNICORN RULE" in PROMPT

    def test_productive_struggle(self):
        assert "PRODUCTIVE STRUGGLE" in PROMPT

    def test_no_gotcha(self):
        assert 'NO GOTCHA, NO "NO."' in PROMPT

    def test_one_concept_per_turn(self):
        assert "ONE CONCEPT PER TURN" in PROMPT

    def test_never_invent(self):
        assert "NEVER INVENT" in PROMPT

    def test_no_offensive_tools(self):
        assert "NO OFFENSIVE TOOLS, EVER" in PROMPT


class TestGradeVocabulary:
    """The four-button recall scale — the scheduler depends on these exact tokens."""

    @pytest.mark.parametrize("grade", ["again", "hard", "good", "easy"])
    def test_grade_present(self, grade):
        assert f"`{grade}`" in PROMPT, f"Grade '{grade}' missing from prompt"


class TestErrorDiagnosisTypes:
    """The four error types in DRILL — silent diagnosis, warm remediation."""

    @pytest.mark.parametrize(
        "error_type",
        [
            "Structural",
            "Deviation",
            "Application",
            "Metacognitive",
        ],
    )
    def test_error_type_present(self, error_type):
        assert f"**{error_type}**" in PROMPT, f"Error type '{error_type}' missing"


class TestCardTypes:
    """Flashcard knowledge types — pinned so they don't get dropped."""

    @pytest.mark.parametrize("card_type", ["[memory]", "[concept]", "[procedure]", "[design]"])
    def test_card_type_present(self, card_type):
        assert card_type in PROMPT, f"Card type '{card_type}' missing"


class TestSentinelTokens:
    """The three sentinel tokens — prompt ↔ frontend contract. Two-sided pin."""

    def test_export_lesson_token(self):
        assert "__EXPORT_LESSON__" in PROMPT

    def test_fix_diagram_token(self):
        assert "__FIX_DIAGRAM__" in PROMPT

    def test_study_token(self):
        assert "__STUDY__" in PROMPT


class TestBloomLadder:
    """The Bloom taxonomy — DRILL targets one level, REFLECT names it."""

    def test_bloom_levels(self):
        for level in ["remember", "understand", "apply", "analyze", "evaluate", "create"]:
            assert level in PROMPT, f"Bloom level '{level}' missing"

    def test_mastery_gate(self):
        assert "MASTERY GATE" in PROMPT
        assert "Apply" in PROMPT


class TestHardNo:
    """The five rules the tutor cannot break."""

    def test_hard_no_section(self):
        assert "HARD NO" in PROMPT

    def test_no_attacks(self):
        assert "Run an attack" in PROMPT or "offensive tool" in PROMPT.lower()

    def test_no_shame(self):
        assert "Shame" in PROMPT or "gotcha" in PROMPT.lower()

    def test_no_walls(self):
        assert "wall of text" in PROMPT.lower() or "one concept" in PROMPT.lower()

    def test_no_inventing(self):
        assert "Inventing" in PROMPT

    def test_no_drifting(self):
        assert "Drifting" in PROMPT or "tangent" in PROMPT.lower()


class TestBannedAbsolutistWords:
    """Hedged language in learner facts — banned absolutist vocabulary."""

    @pytest.mark.parametrize(
        "word",
        [
            "deeply",
            "truly",
            "mastered",
            "expert",
            "passionate",
            "always",
            "never",
        ],
    )
    def test_banned_word_listed(self, word):
        assert word in PROMPT, f"Banned word '{word}' must be listed so the tutor avoids it"


class TestCurriculumSpine:
    """The default curriculum frames — ATT&CK and kill chain."""

    def test_attack_tactics(self):
        assert "MITRE ATT&CK" in PROMPT
        assert "Recon" in PROMPT
        assert "Impact" in PROMPT

    def test_kill_chain(self):
        assert "Cyber Kill Chain" in PROMPT or "kill-chain" in PROMPT.lower()
        assert "Exfiltrate" in PROMPT or "Exfiltration" in PROMPT

    def test_methodology_over_tools(self):
        assert "Methodology over tools" in PROMPT


class TestDiagramDiscipline:
    """Mermaid rules — the gotchas that have burned real lessons."""

    def test_br_tag(self):
        assert "<br/>" in PROMPT

    def test_node_limit(self):
        assert "≤ ~10 nodes" in PROMPT or "10 nodes" in PROMPT

    def test_mermaid_types(self):
        for dtype in ["flowchart", "sequenceDiagram", "stateDiagram-v2", "mindmap"]:
            assert dtype in PROMPT, f"Mermaid type '{dtype}' missing"


class TestRecordReviewDiscipline:
    """The gradebook write path — record_review, NOT kg_assert for drill outcomes."""

    def test_record_review_required(self):
        assert "record_review" in PROMPT

    def test_kg_assert_caveat(self):
        assert "kg_assert" in PROMPT

    def test_learner_subject(self):
        assert "learner:op" in PROMPT
