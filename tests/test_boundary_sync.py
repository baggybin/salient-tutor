"""Two-sided boundary tests — sentinel tokens in sync between prompt and frontend.

The failure mode: a prompt edit removes a token silently. Without the
consumer-side test, the agent emits something the frontend doesn't
recognize. With both sides pinned, the diff breaks the suite first.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PROMPT = (_ROOT / "prompts" / "tutor.md").read_text()
_FRONTEND = (_ROOT / "web" / "static" / "js" / "tutor.js").read_text()


class TestExportTokenSync:
    """__EXPORT_LESSON__ — prompt side + frontend side."""

    def test_in_prompt(self):
        assert "__EXPORT_LESSON__" in _PROMPT

    def test_in_frontend(self):
        assert "__EXPORT_LESSON__" in _FRONTEND


class TestFixDiagramTokenSync:
    """__FIX_DIAGRAM__ — prompt side + frontend side."""

    def test_in_prompt(self):
        assert "__FIX_DIAGRAM__" in _PROMPT

    def test_in_frontend(self):
        assert "__FIX_DIAGRAM__" in _FRONTEND


class TestStudyTokenSync:
    """__STUDY__ — prompt side. (Frontend doesn't use this yet — study mode
    is wired through the daemon, not the web modal in v1.)"""

    def test_in_prompt(self):
        assert "__STUDY__" in _PROMPT


class TestLociFenceSync:
    """The loci fence convention — ```loci in the prompt, parsing in the frontend."""

    def test_loci_fence_in_prompt(self):
        assert "```loci" in _PROMPT or "loci fence" in _PROMPT.lower()

    def test_loci_parser_in_frontend(self):
        assert "loci" in _FRONTEND.lower()
