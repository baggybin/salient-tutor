"""Substring tests for the judge (consensus reconciliation) system prompt."""

from pathlib import Path

PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "judge.md").read_text()


class TestJudgeContract:
    """The verdict shape — pinned so reconciliation output can't drift."""

    def test_nonempty(self):
        assert len(PROMPT.strip()) > 100

    def test_is_judge_persona(self):
        assert "judge" in PROMPT.lower()

    def test_reconciles_agreement(self):
        assert "agree" in PROMPT.lower()

    def test_flags_divergence(self):
        assert "diverge" in PROMPT.lower()

    def test_weighs_credibility(self):
        assert "credible" in PROMPT.lower()

    def test_recommends_answer(self):
        assert "recommend" in PROMPT.lower()

    def test_no_tools(self):
        # The judge is a pure adjudicator — never reads files or delegates.
        assert "No tools" in PROMPT or "no tools" in PROMPT.lower()


class TestPedagogyFilterMode:
    """MODE B — the answer-leakage filter contract (pinned so it can't drift)."""

    def test_declares_two_modes(self):
        assert "MODE A" in PROMPT and "MODE B" in PROMPT

    def test_pedagogy_filter_present(self):
        assert "Pedagogy filter" in PROMPT or "pedagogy filter" in PROMPT.lower()

    def test_leak_concept(self):
        assert "leak" in PROMPT.lower()

    def test_json_contract(self):
        assert '"leaked"' in PROMPT and '"revised"' in PROMPT

    def test_rewrite_to_hint(self):
        assert "rewrite" in PROMPT.lower()

    def test_attempt_first_present(self):
        assert "attempt" in PROMPT.lower()
        assert '"needs_attempt"' in PROMPT or "needs_attempt" in PROMPT

    def test_attempt_pending_flag(self):
        assert "attempt_pending" in PROMPT

    def test_conceptual_exempt(self):
        assert "conceptual" in PROMPT.lower() or "what is" in PROMPT.lower()
