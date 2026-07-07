"""Substring tests for the librarian system prompt."""

from pathlib import Path

PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "librarian.md").read_text()


class TestLibrarianContract:
    """The JSON output contract — pinned so extraction never drifts."""

    def test_status_extracted(self):
        assert '"status": "extracted"' in PROMPT

    def test_status_failed(self):
        assert '"status": "failed"' in PROMPT

    def test_sections_key(self):
        assert '"sections"' in PROMPT

    def test_key_facts_key(self):
        assert '"key_facts"' in PROMPT

    def test_drills_key(self):
        assert '"drills"' in PROMPT

    def test_chunks_key(self):
        assert '"chunks"' in PROMPT

    def test_diagram_hint_key(self):
        assert '"diagram_hint"' in PROMPT

    def test_prereq_key(self):
        assert '"prereq"' in PROMPT

    def test_total_pages_key(self):
        assert '"total_pages"' in PROMPT


class TestLibrarianRules:
    """The hard rules — break any and the librarian becomes unsafe."""

    def test_read_only_given_path(self):
        assert "Read ONLY the path you were given" in PROMPT

    def test_no_other_tools(self):
        assert "No other tools" in PROMPT

    def test_never_invent(self):
        assert "Never invent" in PROMPT

    def test_preserve_meaning(self):
        assert "Preserve the source" in PROMPT or "preserve" in PROMPT.lower()

    def test_end_your_turn(self):
        assert "end your turn" in PROMPT.lower()

    def test_keep_compact(self):
        assert "compact" in PROMPT.lower() or "single reply" in PROMPT.lower()
