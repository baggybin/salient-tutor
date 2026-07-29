"""Locations of the tutor's WRITABLE state — the learner's own work.

Workspaces ("schoolbags": chats, knowledge graph, gradebook, review logs, agent
configs, images) and the pointer to the last-used one. These used to sit at the
repo root, which is fine in a source checkout and wrong once installed: the
package then lives in site-packages, which is the wrong home for a user's work
and is frequently not writable at all.

Resolved through :func:`platformdirs.user_data_path`, so an installed launch
writes somewhere that exists, is writable, and survives reinstalling the
package. Deliberately NOT the launch directory: `cwd` makes a learner's history
silently depend on which folder they happened to start from.

Read-only bundled resources are a different question — see
:mod:`salient_tutor.resource_paths`.
"""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

from platformdirs import user_data_path

_APP = "salient-tutor"

# The pointer the pre-packaging layout wrote at the repo root. Still read ONCE,
# so an existing checkout keeps autoloading the workspace it always did; never
# moved or deleted, because it is the learner's data and a downgrade must still
# find it.
_LEGACY_POINTER = Path(__file__).resolve().parents[2] / ".salient-tutor-workspace"


def state_root() -> Path:
    """Base directory for this user's tutor state."""
    return user_data_path(_APP)


def pointer_path() -> Path:
    """File recording the last-used workspace, so a plain launch resumes it."""
    return state_root() / "last-workspace"


def default_work_root() -> Path:
    """Where a brand-new workspace goes when nothing else is specified."""
    return state_root() / "work"


def _read_pointer(path: Path) -> Path | None:
    try:
        raw = path.read_text().strip()
    except OSError:
        return None
    return Path(raw).resolve() if raw else None


def read_last_workspace() -> Path | None:
    """The workspace remembered from a previous run, or None.

    Falls back to the legacy repo-root pointer once, and adopts it, so an
    existing source checkout does not appear to lose its history the first time
    it runs on the packaged layout. The legacy file is left exactly as it is.
    """
    current = _read_pointer(pointer_path())
    if current is not None:
        return current
    legacy = _read_pointer(_LEGACY_POINTER)
    if legacy is not None:
        remember_workspace(legacy)
    return legacy


def remember_workspace(path: Path) -> None:
    """Persist `path` as the last-used workspace.

    Best-effort on the write itself, but the parent directory is created
    deliberately: an unwritable state root should surface as a real error at
    startup rather than as a pointer that silently never persists.
    """
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        pointer_path().write_text(str(path))


def resolve_env_work_root() -> Path | None:
    """`TUTOR_WORK_ROOT`, if set. Still wins over everything else.

    A relative value resolves against the state root rather than the launch
    directory, so its meaning does not change with cwd.
    """
    env = os.environ.get("TUTOR_WORK_ROOT")
    if not env:
        return None
    p = Path(env).expanduser()
    return p.resolve() if p.is_absolute() else (state_root() / p).resolve()
