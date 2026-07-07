"""Tests for the Obsidian lesson export module."""

from salient_tutor.export import (
    _extract_title,
    _stamp_created,
    _unwrap_fence,
    export_lesson,
    lessons_dir,
    slugify,
)


class TestSlugify:
    def test_basic(self):
        assert slugify("Photosynthesis Basics") == "photosynthesis-basics"

    def test_special_chars(self):
        assert slugify("Cells: Membranes & Organelles!") == "cells-membranes-organelles"

    def test_empty_falls_back(self):
        assert slugify("") == "lesson"
        assert slugify("!!!") == "lesson"

    def test_max_length(self):
        long = "a" * 100
        result = slugify(long, max_len=60)
        assert len(result) <= 60

    def test_unicode(self):
        assert slugify("Café Résumé") == "caf-r-sum"


class TestUnwrapFence:
    def test_markdown_fence(self):
        body = "```markdown\n# Title\nContent\n```"
        assert _unwrap_fence(body) == "# Title\nContent"

    def test_md_fence(self):
        body = "```md\nContent\n```"
        assert _unwrap_fence(body) == "Content"

    def test_plain_fence(self):
        body = "```\nContent\n```"
        assert _unwrap_fence(body) == "Content"

    def test_no_fence(self):
        assert _unwrap_fence("# Title\nContent") == "# Title\nContent"


class TestStampCreated:
    def test_adds_to_frontmatter(self):
        body = "---\ntitle: Test\n---\n# Content"
        result = _stamp_created(body, now="2026-06-30T12:00:00Z")
        assert "created: 2026-06-30T12:00:00Z" in result

    def test_updates_existing(self):
        body = "---\ntitle: Test\ncreated: old\n---\n# Content"
        result = _stamp_created(body, now="2026-06-30T12:00:00Z")
        assert "created: 2026-06-30T12:00:00Z" in result
        assert "old" not in result.split("---")[1]

    def test_no_frontmatter_unchanged(self):
        body = "# No frontmatter"
        result = _stamp_created(body, now="2026-06-30T12:00:00Z")
        assert result == "# No frontmatter"


class TestExtractTitle:
    def test_explicit_arg(self):
        assert _extract_title("body", explicit="My Title") == "My Title"

    def test_frontmatter_title(self):
        body = '---\ntitle: "From FM"\n---\n# Heading'
        assert _extract_title(body) == "From FM"

    def test_heading(self):
        body = "# My Heading\nContent"
        assert _extract_title(body) == "My Heading"

    def test_fallback(self):
        assert _extract_title("no title anywhere") == "lesson"


class TestExportLesson:
    def test_full_export(self, tmp_path):
        body = (
            "```markdown\n"
            "---\n"
            "title: Photosynthesis\n"
            "type: lesson\n"
            "---\n\n"
            "# Photosynthesis\n\n"
            "Content here.\n"
            "```"
        )
        path = export_lesson(body, work_root=tmp_path, now="2026-06-30T12:00:00Z")
        assert path.exists()
        assert path.name == "photosynthesis.md"
        assert path.parent == tmp_path / "lessons"
        content = path.read_text()
        assert "created: 2026-06-30T12:00:00Z" in content
        assert "# Photosynthesis" in content

    def test_creates_lessons_dir(self, tmp_path):
        path = export_lesson("# Test\nContent", work_root=tmp_path)
        assert path.exists()
        assert (tmp_path / "lessons").is_dir()

    def test_idempotent_stamp(self, tmp_path):
        body = "---\ntitle: Test\n---\n# Test"
        path1 = export_lesson(body, work_root=tmp_path, now="2026-06-30T12:00:00Z")
        content1 = path1.read_text()
        path2 = export_lesson(content1, work_root=tmp_path, now="2026-07-01T12:00:00Z")
        content2 = path2.read_text()
        assert "2026-07-01" in content2
        assert "2026-06-30" not in content2


class TestLessonsDir:
    def test_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = lessons_dir()
        assert d == tmp_path / "work" / "lessons"
        assert d.is_dir()

    def test_explicit(self, tmp_path):
        d = lessons_dir(tmp_path)
        assert d == tmp_path / "lessons"
        assert d.is_dir()
