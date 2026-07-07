"""Headless live smoke test — judge pedagogy filter on DeepSeek.

Run from the salient-tutor repo root with the DeepSeek key already in
ANTHROPIC_API_KEY (auth_style=api_key for DeepSeek):

    export TUTOR_PROVIDER=deepseek
    export TUTOR_JUDGE_MODEL=deepseek-chat
    export TUTOR_JUDGE_PROVIDER=deepseek
    .venv/bin/python scripts/smoke_judge_deepseek.py

Confirms (a) the env-seeded DeepSeek routing reaches a real model and (b) the
P0-B pedagogy filter flags a leaked solution and rewrites it to a hint.
"""

import asyncio

from salient_tutor.daemon import TutorDaemon


async def main() -> None:
    d = TutorDaemon()
    ep = d._agent_endpoint_for("judge")
    print("judge routing:", "anthropic(inherited)" if ep is None else (ep[5], ep[0]))
    print("judge_enabled:", d.judge_enabled())
    if not d.judge_enabled():
        print("!! no judge configured — set TUTOR_JUDGE_MODEL + TUTOR_JUDGE_PROVIDER")
        return

    # Skip d.start() (it would also spin up the local librarian runner);
    # pedagogy_filter -> prompt("judge") starts only the judge runner.
    try:
        # Phase 1 — attempt-first gate: a fresh problem question with no prior
        # attempt should return needs_attempt=True at every strictness level.
        print("\n== Phase 1: attempt-first gate (attempt_pending=False) ==")
        gate_q = "how do I kerberoast a service account?"
        gate_draft = (
            "Sure — run `GetUserSPNs.py -request`, grab the TGS hash, then feed it "
            "to `hashcat -m 13100` with rockyou.txt to crack the password."
        )
        for level in ("explain", "socratic", "bare"):
            res = await d.pedagogy_filter(gate_q, gate_draft, strictness=level)
            print(f"[{level}] leaked={res['leaked']} needs_attempt={res['needs_attempt']}")
            print("  revised:", res["revised"][:260])

        # Phase 2 — leakage filter: the learner has attempted, so the gate is
        # cleared and the leak/strictness rewrite path runs. Expect
        # explain→passthrough, socratic/bare→leaked + progressively tighter hint.
        print("\n== Phase 2: leakage filter + strictness dial (attempt_pending=True) ==")
        leak_q = "I think I request a TGS ticket for the SPN and crack it offline — is that right?"
        leak_draft = (
            "Exactly. Run GetUserSPNs.py -request to get the TGS hash, then "
            "hashcat -m 13100 with rockyou.txt to recover the plaintext password."
        )
        for level in ("explain", "socratic", "bare"):
            res = await d.pedagogy_filter(
                leak_q, leak_draft, strictness=level, attempt_pending=True
            )
            print(f"[{level}] leaked={res['leaked']} needs_attempt={res['needs_attempt']}")
            print("  revised:", res["revised"][:260])
    finally:
        for runner in d.runners.values():
            await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
