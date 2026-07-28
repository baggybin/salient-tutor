"""Codex tool calls pass a policy gate before the handler runs.

`TutorDaemon` builds its own `ToolBundle` and calls `provider.create_backend()`
directly — it does not compose salient-core's `AgentRunnerFactory`. Codex then
executes those handlers straight through its MCP gateway, so none of the
Claude-SDK PreToolUse hooks apply. That is the same structural hole the kernel
closed for its own daemon, and left open here.

We now apply the kernel's shared wrapper (`runtime.gate_tool_bundle`) rather
than reimplementing the seam. Only ONE rung makes sense here: the
prohibited-intent check. `approve_before` does not — the tutor has no
approval-answer surface, so blocking on an inbox future would hang the turn with
nobody able to release it.

The kernel ships the mechanism with an EMPTY default denylist (the offensive
content lives in salient-security, which the tutor does not install), so what
fires is whatever the deployment configures under `safeguards.extra_patterns`.
These pins therefore configure a pattern and prove it bites.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from salient_core.runtime import AgentTool, PolicyDenied, ToolBundle, gate_tool_bundle

from salient_tutor.daemon import TutorDaemon

_PATTERN = "OPERATION-QUARTZ"


def _daemon(extra_patterns: dict[str, Any] | None = None) -> TutorDaemon:
    """A bare daemon with just the surface `_make_safeguard_check` touches."""
    d = TutorDaemon.__new__(TutorDaemon)
    d.profile = (
        {"safeguards": {"extra_patterns": extra_patterns}} if extra_patterns is not None else {}
    )
    d.agent_configs = {"tutor": {}}
    return d


def _gate(daemon: TutorDaemon, calls: list[dict[str, Any]], *, as_bus: bool = True) -> Any:
    async def handler(args):
        calls.append(dict(args))
        return {"ran": True}

    bundle = ToolBundle((AgentTool("ask_agents", "", {"type": "object"}, handler),))
    return (
        gate_tool_bundle(
            bundle,
            agent_name="tutor",
            server="tutor",
            checks=[daemon._make_safeguard_check("tutor")],
            bus_tool_names=frozenset({"ask_agents"}) if as_bus else frozenset(),
        )
        .tools[0]
        .handler
    )


@pytest.mark.anyio
async def test_a_configured_pattern_refuses_the_call() -> None:
    calls: list[dict[str, Any]] = []
    handler = _gate(_daemon({"delegation": [{"label": "codename", "pattern": _PATTERN}]}), calls)

    with pytest.raises(PolicyDenied) as caught:
        await handler({"prompt": f"brief the team on {_PATTERN}"})

    assert "codename" in str(caught.value)
    assert calls == [], "handler ran despite a refusal"


@pytest.mark.anyio
async def test_benign_prose_still_runs() -> None:
    calls: list[dict[str, Any]] = []
    handler = _gate(_daemon({"delegation": [{"label": "codename", "pattern": _PATTERN}]}), calls)

    assert await handler({"prompt": "explain binary search"}) == {"ran": True}
    assert calls == [{"prompt": "explain binary search"}]


@pytest.mark.anyio
async def test_no_configured_patterns_is_an_honest_no_op() -> None:
    """An empty denylist must pass calls through, not pretend to gate."""
    calls: list[dict[str, Any]] = []
    handler = _gate(_daemon(), calls)

    assert await handler({"prompt": f"anything at all, even {_PATTERN}"}) == {"ran": True}
    assert len(calls) == 1


@pytest.mark.anyio
async def test_bus_tools_must_be_named_or_the_denylist_misses_them() -> None:
    """Why `bus_tool_names` is load-bearing rather than decoration.

    Bus tools canonicalize to `bus.<name>`; the per-agent form would be
    `tutor.ask_agents`, which matches no `bus.*` pattern. Omitting the set
    silently costs the delegation denylist — the failure this whole gate exists
    to prevent.
    """
    daemon = _daemon({"delegation": [{"label": "codename", "pattern": _PATTERN}]})
    prompt = {"prompt": f"brief the team on {_PATTERN}"}

    named: list[dict[str, Any]] = []
    with pytest.raises(PolicyDenied):
        await _gate(daemon, named, as_bus=True)(prompt)

    unnamed: list[dict[str, Any]] = []
    await _gate(daemon, unnamed, as_bus=False)(prompt)  # slips through
    assert unnamed == [prompt]


@pytest.mark.anyio
async def test_an_unparseable_wire_name_does_not_crash_the_gate() -> None:
    """No key to look up is not the same as a crash mid-turn."""
    daemon = _daemon({"delegation": [{"label": "codename", "pattern": _PATTERN}]})
    check = daemon._make_safeguard_check("tutor")

    assert await check({"tool_name": "not-an-mcp-name", "tool_input": {}}, "id", None) == {}
    assert await check({}, "id", None) == {}


def test_the_factory_actually_gates_the_bundle_it_builds() -> None:
    """Wiring pin: the gate must be applied where the bundle is built.

    A behavioural test would need a live codex backend; this asserts against the
    real source that `_make_codex_backend_factory` both wraps the bundle and
    names the bus tools, so the wiring cannot be dropped unnoticed.
    """
    import inspect

    src = inspect.getsource(TutorDaemon._make_codex_backend_factory)

    assert "gate_tool_bundle(" in src, "codex bundle is no longer gated"
    assert "bus_tool_names=" in src, "bus tools unnamed — bus.* patterns would miss"
    assert src.index("gate_tool_bundle(") < src.index("create_backend("), (
        "the bundle must be gated BEFORE it reaches the backend"
    )


@pytest.mark.anyio
async def test_asyncio_gather_of_gated_calls_is_safe() -> None:
    """Concurrent tutor turns must not collide in the gate."""
    calls: list[dict[str, Any]] = []
    handler = _gate(_daemon(), calls)

    results = await asyncio.gather(*(handler({"i": i}) for i in range(4)))

    assert results == [{"ran": True}] * 4
    assert len(calls) == 4
