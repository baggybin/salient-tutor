"""Read-containment PreToolUse hook for the librarian agent.

Confines local file-reading built-ins (Read / Grep / Glob) to the study
uploads tree. Built-ins bypass the safeguard + scope hooks, so a Read
grant is otherwise completely ungated. This hook closes that hole.

Opt-in per agent (only the librarian uses it). The allowed root is
resolved at call time, and the target is ``resolve()``d (collapsing
``..`` and symlinks) before a trailing-separator prefix check, so neither
path traversal nor a sibling-prefix masquerade can slip through.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def make_read_containment_hook(
    daemon: Any,
    agent_name: str,
    study_root_fn: Any = None,
):
    """Build a PreToolUse hook confining Read/Grep/Glob to the study tree.

    Args:
        daemon: The TutorDaemon (provides ``runners`` for per-dispatch overrides).
        agent_name: The agent this hook is registered for.
        study_root_fn: Callable returning the study root Path. Defaults to
                       ``salient_tutor.study.study_root``.
    """
    if study_root_fn is None:
        from salient_tutor.study import study_root as study_root_fn

    read_tools = {"Read", "Grep", "Glob"}

    async def hook(input_data, tool_use_id, context):  # noqa: ARG001
        tool_name = (input_data or {}).get("tool_name") or ""
        if tool_name not in read_tools:
            return {}
        ti = (input_data or {}).get("tool_input") or {}
        # A dispatch can NARROW the root to one project's uploads dir
        runner = daemon.runners.get(agent_name) if hasattr(daemon, "runners") else None
        override = getattr(runner, "_study_read_root", None) if runner else None
        allowed = (Path(override) if override else study_root_fn()).resolve()

        base = ti.get("path") or ti.get("file_path") or ""
        candidates = [ti.get("file_path"), ti.get("path"), ti.get("pattern"), ti.get("glob")]
        offending = None
        for raw_c in candidates:
            if not raw_c:
                continue
            try:
                p = Path(raw_c)
                target = (p if p.is_absolute() else Path(base or ".") / p).resolve()
            except (OSError, ValueError, RuntimeError):
                offending = raw_c
                break
            if not (target == allowed or str(target).startswith(str(allowed) + os.sep)):
                offending = raw_c
                break

        raw = offending if offending is not None else (base or "(no path)")
        ok = offending is None and any(candidates)
        if not ok:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{tool_name} is confined to the study uploads tree "
                        f"({allowed}); {raw!r} is outside it. You may only "
                        f"read the document path handed to you."
                    ),
                }
            }
        return {}

    return hook
