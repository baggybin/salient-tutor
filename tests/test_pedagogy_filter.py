"""Judge pedagogy filter — TutorDaemon.pedagogy_filter.

Drives the real method with a stubbed ``prompt`` (no runner stack, no API key),
covering leak/clean/passthrough/failure paths and strictness threading.

No pytest-asyncio in this repo — coroutines run via asyncio.run.
"""

from __future__ import annotations

import asyncio

from salient_tutor.daemon import TutorDaemon


def _daemon(tmp_path, monkeypatch, *, reply=None, with_judge=True, raises=False):
    """A TutorDaemon on a tmp work_root with a canned/failing judge prompt.

    Captures the prompt text sent to the judge in ``d.last_prompt`` so tests can
    assert strictness threading.
    """
    monkeypatch.delenv("TUTOR_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TUTOR_VARIANT_MODEL", raising=False)
    d = TutorDaemon(work_root=tmp_path / "work")
    d.agent_configs = {"tutor": {}}
    if with_judge:
        d.agent_configs["judge"] = {}
    d.last_prompt = None
    d.called = False

    async def _fake_prompt(agent, message, *, timeout=120.0):
        d.called = True
        d.last_prompt = message
        if raises:
            raise RuntimeError("judge exploded")
        return reply

    monkeypatch.setattr(d, "prompt", _fake_prompt)
    return d


def test_leaky_draft_is_rewritten(tmp_path, monkeypatch):
    d = _daemon(
        tmp_path,
        monkeypatch,
        reply='{"needs_attempt": false, "leaked": true, "revised": "What property of the account matters?"}',
    )
    out = asyncio.run(d.pedagogy_filter("how do I kerberoast?", "Request a TGS then hashcat…"))
    assert out == {
        "leaked": True,
        "needs_attempt": False,
        "revised": "What property of the account matters?",
    }


def test_clean_draft_passthrough(tmp_path, monkeypatch):
    draft = "Kerberoasting targets service accounts — what makes them special?"
    d = _daemon(
        tmp_path,
        monkeypatch,
        reply='{"needs_attempt": false, "leaked": false, "revised": "ignored"}',
    )
    out = asyncio.run(d.pedagogy_filter("q", draft))
    # not leaked → echoes the original draft, never the judge's 'revised'
    assert out == {"leaked": False, "needs_attempt": False, "revised": draft}


def test_no_judge_configured_is_passthrough(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, with_judge=False)
    out = asyncio.run(d.pedagogy_filter("q", "some draft"))
    assert out == {"leaked": False, "needs_attempt": False, "revised": "some draft"}
    assert d.called is False  # judge never invoked


def test_empty_draft_is_passthrough(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply='{"leaked": true, "revised": "x"}')
    out = asyncio.run(d.pedagogy_filter("q", "   "))
    assert out == {"leaked": False, "needs_attempt": False, "revised": "   "}
    assert d.called is False


def test_judge_failure_degrades_to_passthrough(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, raises=True)
    out = asyncio.run(d.pedagogy_filter("q", "draft"))
    assert out == {"leaked": False, "needs_attempt": False, "revised": "draft"}


def test_non_json_reply_degrades_to_passthrough(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply="sorry, I can't produce JSON")
    out = asyncio.run(d.pedagogy_filter("q", "draft"))
    assert out == {"leaked": False, "needs_attempt": False, "revised": "draft"}


def test_fresh_problem_elicits_attempt(tmp_path, monkeypatch):
    d = _daemon(
        tmp_path,
        monkeypatch,
        reply='{"needs_attempt": true, "leaked": false, "revised": "What kind of account is a good target?"}',
    )
    out = asyncio.run(d.pedagogy_filter("how do I kerberoast?", "Here is how you kerberoast: …"))
    assert out == {
        "leaked": False,
        "needs_attempt": True,
        "revised": "What kind of account is a good target?",
    }


def test_attempt_turn_is_not_regated(tmp_path, monkeypatch):
    # Even if the judge slips and asks for another attempt, attempt_pending=True
    # suppresses it — the learner just attempted.
    d = _daemon(
        tmp_path,
        monkeypatch,
        reply='{"needs_attempt": true, "leaked": false, "revised": "try again"}',
    )
    out = asyncio.run(
        d.pedagogy_filter("the SPN account?", "Good — here's why…", attempt_pending=True)
    )
    assert out["needs_attempt"] is False
    assert out["revised"] == "Good — here's why…"  # draft passes through


def test_attempt_pending_reaches_the_judge_prompt(tmp_path, monkeypatch):
    d = _daemon(
        tmp_path, monkeypatch, reply='{"needs_attempt": false, "leaked": false, "revised": "x"}'
    )
    asyncio.run(d.pedagogy_filter("q", "draft", attempt_pending=True))
    assert "attempt_pending=True" in d.last_prompt


def test_strictness_reaches_the_judge_prompt(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply='{"leaked": false, "revised": "x"}')
    asyncio.run(d.pedagogy_filter("q", "draft", strictness="bare"))
    assert "level: bare" in d.last_prompt
    assert "STRICT" in d.last_prompt  # the 'bare' rubric text


def test_invalid_strictness_falls_back_to_socratic(tmp_path, monkeypatch):
    d = _daemon(tmp_path, monkeypatch, reply='{"leaked": false, "revised": "x"}')
    asyncio.run(d.pedagogy_filter("q", "draft", strictness="nonsense"))
    assert "level: socratic" in d.last_prompt


def test_judge_enabled_flag(tmp_path, monkeypatch):
    assert _daemon(tmp_path, monkeypatch, with_judge=True).judge_enabled() is True
    assert _daemon(tmp_path, monkeypatch, with_judge=False).judge_enabled() is False
