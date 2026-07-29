"""Locations of the tutor's READ-ONLY runtime resources.

Prompts, curricula, the pedagogy bundle and the web UI ship inside the
distribution. They used to be resolved as ``Path(__file__).parents[2] / …``,
which is the repo root in a source checkout and ``<venv>/lib/python3.X`` once
installed — so a non-editable ``pip install salient-tutor`` produced a build that
raised ``FileNotFoundError: …/python3.12/prompts/librarian.md`` and refused to
mount its own static directory. They also were not packaged at all, because
``[tool.setuptools.packages.find]`` collects Python packages and these lived at
the repo root.

Resolved through :func:`importlib.resources.files` against
``salient_tutor.resources`` so the answer comes from the installed package
rather than from a guess about where the source tree is.

Writable state is a different question with a different answer — see
:mod:`salient_tutor.state_paths`. Never write under here.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

# `files()` returns a Traversable. Every supported install (wheel, sdist,
# editable) unpacks to a real directory, so materializing a Path here keeps the
# many `Path`-typed consumers — StaticFiles mounts, `.glob()`, `.read_text()` —
# working unchanged. A zip-import would need `as_file`; that is not a supported
# deployment for this app, and this would fail loudly rather than silently.
RESOURCES: Path = Path(str(files("salient_tutor.resources")))

#: Agent system prompts (`tutor.md`, `librarian.md`, `judge.md`, `skills/…`).
PROMPTS: Path = RESOURCES / "prompts"

#: Seed data: the pedagogy bundle and the published curricula.
DATA: Path = RESOURCES / "data"

#: The vanilla-JS operator UI mounted at `/`.
WEB_STATIC: Path = RESOURCES / "web" / "static"


def require(path: Path, what: str) -> Path:
    """Return `path`, or raise a typed error naming what is missing.

    A resource absent from an installed build is a packaging fault, not a user
    error, so it should fail immediately and say so — not surface later as a
    confusing empty roster or a blank page.
    """
    if not path.exists():
        raise ResourceMissingError(what, path)
    return path


class ResourceMissingError(RuntimeError):
    """A bundled resource is absent — the distribution is incomplete."""

    def __init__(self, what: str, path: Path) -> None:
        self.what = what
        self.path = path
        super().__init__(
            f"bundled resource missing: {what} (expected at {path}). "
            f"This build of salient-tutor is incomplete — reinstall it, and if "
            f"that does not fix it the package data declaration has regressed."
        )
