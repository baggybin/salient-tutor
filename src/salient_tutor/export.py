"""Obsidian lesson export — slugify, stamp, write to disk.

The tutor replies with a single ```markdown block (the __EXPORT_LESSON__
contract). This module stamps it, slugs the title, and writes the note
to <work_root>/lessons/.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path


def slugify(title: str, *, max_len: int = 60) -> str:
    """Lowercase, hyphenated, non-alnum → -, max ~60 chars, fallback 'lesson'."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower().strip(), flags=re.UNICODE)
    slug = slug.strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0] if "-" in slug[:max_len] else slug[:max_len]
    return slug or "lesson"


def lessons_dir(work_root: Path | str | None = None) -> Path:
    """Resolve <work_root>/lessons/, creating on demand."""
    root = Path(work_root) if work_root else Path.cwd() / "work"
    d = root / "lessons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _unwrap_fence(body: str) -> str:
    """Tolerantly strip a single ```markdown / ```md fence wrapper."""
    stripped = body.strip()
    for lang in ("markdown", "md"):
        prefix = f"```{lang}"
        if stripped.startswith(prefix):
            lines = stripped.split("\n")[1:]  # drop the opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.split("\n")[1:-1]
        return "\n".join(lines).strip()
    return stripped


def _stamp_created(body: str, *, now: str | None = None) -> str:
    """Insert or update `created:` in the YAML frontmatter."""
    ts = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not body.startswith("---"):
        return body

    end = body.find("\n---", 3)
    if end == -1:
        return body

    fm = body[3:end]
    if re.search(r"^created:\s*", fm, re.MULTILINE):
        fm = re.sub(r"^created:.*$", f"created: {ts}", fm, flags=re.MULTILINE)
    else:
        fm = fm.rstrip() + f"\ncreated: {ts}\n"
    return "---" + fm + body[end:]


def _extract_title(body: str, *, explicit: str | None = None) -> str:
    """Title precedence: explicit arg > frontmatter title: > first # heading > 'lesson'."""
    if explicit:
        return explicit

    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            m = re.search(r"^title:\s*(.+)$", body[3:end], re.MULTILINE)
            if m:
                return m.group(1).strip().strip('"').strip("'")

    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()

    return "lesson"


def export_lesson(
    body: str,
    *,
    title: str | None = None,
    work_root: Path | str | None = None,
    now: str | None = None,
) -> Path:
    """Export a tutor lesson reply to an Obsidian note on disk.

    1. Unwrap the ```markdown fence if present.
    2. Extract the title (explicit > frontmatter > heading > 'lesson').
    3. Stamp `created:` into the frontmatter.
    4. Slugify the title → filename.
    5. Write to <work_root>/lessons/<slug>.md.

    Returns the path to the written file.
    """
    unwrapped = _unwrap_fence(body)
    resolved_title = _extract_title(unwrapped, explicit=title)
    stamped = _stamp_created(unwrapped, now=now)
    slug = slugify(resolved_title)
    out_dir = lessons_dir(work_root)
    out_path = out_dir / f"{slug}.md"
    out_path.write_text(stamped, encoding="utf-8")
    return out_path
