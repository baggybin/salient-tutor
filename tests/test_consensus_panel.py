"""Second-opinion consensus panel — TutorDaemon.second_opinion wiring.

Drives the real daemon method (which builds the ask_agent shim and invokes the
kernel's ask_consensus) with a canned `prompt` and fake runners, so panel
resolution, dispatch, synthesis, and the judge gate are exercised without the
real runner stack or an API key.

No pytest-asyncio in this repo — tests drive the coroutine via asyncio.run.
"""

from __future__ import annotations

import asyncio

from salient_tutor.daemon import TutorDaemon, _build_agent_configs


class _Runner:
    def __init__(self, status: str = "idle"):
        self.status = status


def _panel_daemon(tmp_path, monkeypatch, *, replies, with_alt=True, with_judge=False):
    """A TutorDaemon on a tmp work_root with fake runners and a canned prompt.

    `replies` maps agent name → reply text. Runners exist for every name in
    `replies` so resolve_panel treats them as live.
    """
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    d = TutorDaemon(work_root=tmp_path / "work")
    d.agent_configs = {"tutor": {}}
    if with_alt:
        d.agent_configs["tutor_alt"] = {"substitute_for": "tutor"}
    if with_judge:
        d.agent_configs["judge"] = {}
    d.runners = {name: _Runner("idle") for name in replies}

    async def _fake_prompt(agent, message, *, timeout=120.0):
        return replies.get(agent, f"(no canned reply for {agent})")

    monkeypatch.setattr(d, "prompt", _fake_prompt)
    return d


def test_second_opinion_returns_panel_payload(tmp_path, monkeypatch):
    d = _panel_daemon(
        tmp_path,
        monkeypatch,
        replies={
            "tutor": "Photosynthesis converts CO2 and water into glucose in the chloroplast.",
            "tutor_alt": "In the chloroplast, photosynthesis turns water and CO2 into glucose.",
        },
    )
    p = asyncio.run(d.second_opinion("teach me photosynthesis"))

    assert p["ok"] is True
    assert set(p["panel"]) == {"tutor", "tutor_alt"}
    assert len(p["per_agent"]) == 2
    assert all(r["ok"] for r in p["per_agent"])
    assert isinstance(p["agreement_score"], float)
    assert p["judge"] is None  # no judge configured


def test_second_opinion_without_judge_has_no_warning(tmp_path, monkeypatch):
    d = _panel_daemon(
        tmp_path,
        monkeypatch,
        replies={
            "tutor": "alpha beta",
            "tutor_alt": "alpha gamma",
        },
    )
    p = asyncio.run(d.second_opinion("q"))
    # judge='off' path → no "judge unavailable" warning
    assert "judge" not in (w.lower() for w in p.get("warnings", []))


def test_second_opinion_needs_two_agents(tmp_path, monkeypatch):
    d = _panel_daemon(tmp_path, monkeypatch, replies={"tutor": "solo"}, with_alt=False)
    p = asyncio.run(d.second_opinion("q"))
    assert p["ok"] is False
    assert "2" in p["error"] or "two" in p["error"].lower()


def test_judge_config_registered_from_env(monkeypatch):
    monkeypatch.setenv("TUTOR_VARIANT_MODEL", "some-variant-model")
    monkeypatch.setenv("TUTOR_JUDGE_MODEL", "some-judge-model")
    configs = _build_agent_configs()
    assert "judge" in configs
    assert configs["judge"]["model"] == "some-judge-model"
    assert configs["judge"]["system_prompt_file"] == "judge.md"
    # tutor_alt is marked as tutor's shadow for native panel resolution
    assert configs["tutor_alt"]["substitute_for"] == "tutor"


def test_no_judge_config_when_env_unset(monkeypatch):
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    configs = _build_agent_configs()
    assert "judge" not in configs


def test_judge_and_variant_registered_from_persisted_config(monkeypatch):
    # No env at all — the roster is driven entirely by agent_configs.json.
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_PROVIDER", raising=False)
    runtime = {
        "judge": {"provider": "minimax", "model": "MiniMax-M2"},
        "tutor_alt": {"provider": "deepseek", "model": "deepseek-chat"},
    }
    configs = _build_agent_configs(runtime)
    assert configs["judge"]["model"] == "MiniMax-M2"
    assert configs["judge"]["system_prompt_file"] == "judge.md"
    assert configs["tutor_alt"]["model"] == "deepseek-chat"
    assert configs["tutor_alt"]["substitute_for"] == "tutor"
    # deepseek variant drops the Anthropic-only builtin tools upfront
    assert configs["tutor_alt"]["builtin_tools"] == []


def test_env_model_wins_over_persisted_when_both(monkeypatch):
    monkeypatch.setenv("TUTOR_JUDGE_MODEL", "env-judge")
    runtime = {"judge": {"provider": "minimax", "model": "config-judge"}}
    configs = _build_agent_configs(runtime)
    assert configs["judge"]["model"] == "env-judge"


def test_anthropic_block_without_model_does_not_register(monkeypatch):
    # A {provider: anthropic, effort: low} block (no model) is only a runtime
    # override for an agent registered elsewhere — it must NOT spawn a judge.
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    runtime = {"judge": {"provider": "anthropic", "effort": "low"}}
    configs = _build_agent_configs(runtime)
    assert "judge" not in configs
