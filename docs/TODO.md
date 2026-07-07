# salient-tutor — open TODOs

> Snapshot 2026-07-02 (branch `harden-integration`). Companion to
> [`design-research.md`](./design-research.md) (the evidence) and
> [`p0-implementation-plan.md`](./p0-implementation-plan.md).

## 🔴 Blocking / infra

- [ ] **Add the `SALIENT_CORE_TOKEN` CI secret.** The CI `test` job clones the
      private `baggybin/salient-core` and fails until this exists. Create a
      fine-grained PAT (resource owner `baggybin`, repo `salient-core`,
      **Contents: Read**) and add it under salient-tutor → Settings → Secrets and
      variables → Actions as `SALIENT_CORE_TOKEN`. Lint job is already green.
      *(Owner action — I can't create secrets.)*
- [ ] **Live end-to-end smoke** (needs an API key; nothing below is verified
      against a real model yet — only unit tests + `node --check`). With
      `TUTOR_VARIANT_MODEL` + `TUTOR_JUDGE_MODEL` set, run
      `python -m salient_tutor.web` and exercise: consensus "second opinion",
      the attempt-first gate + judge leakage filter (reviewed turns), the
      retrieval quiz card, and the 🗺 prerequisite-DAG map.

## 🟡 Remaining P2 features (from design-research.md)

- [ ] **Consensus-panel trust reframing.** Research (findings 8–9): agreement ≠
      correctness; CoT traces / LLM citations are post-hoc. Reframe the existing
      second-opinion card — relabel score chips ("models agree", not
      "confidence"), add a one-line "⚠ agreement ≠ correctness — verify against
      sources", and gate the judge verdict behind a "review before accepting"
      click (deliberate friction) rather than auto-expanded.
- [ ] **Verified inline KB citations.** When the tutor asserts a fact, cite the
      KB triple it came from — and **verify the citation resolves** against the KG
      (`read_evidence` / `kg_query`) before rendering, since LLM citations are
      often reverse-engineered.

## 🟢 Follow-ups / hardening

- [ ] **UNICORN RULE — the "both" option.** Currently generalized to "show the
      whole coin" as a PRIME DIRECTIVE. To make it non-negotiable: add a HARD NO
      ("teach a technique without its other side / detection") and restate it in
      the MODEL teaching phase (§2), where teaching actually happens.
- [ ] **Generalize the export "Defender's view" heading.** The export contract's
      `## Defender's view` is security-flavored; broaden to "the other side" to
      match the generalized UNICORN RULE for non-security lessons.
- [ ] **CI kernel pin.** CI installs `salient-core@harden-public-api` (moving
      branch). When the kernel is released / merged to `main` (PLAN.md P5), switch
      to a version pin for reproducibility.
- [ ] **Public export for `make_consensus_tools`.** `TutorDaemon.second_opinion`
      imports from the private `salient_core.bus._consensus`. Add a lazy public
      export on the kernel so the tutor doesn't reach into a `_` module.
- [ ] **Skill-map staleness.** New gradebook topics added after the prerequisite
      DAG is generated aren't edged until a rebuild. Consider an incremental
      "add edges for new topics only" pass.

## ✅ Done this session (for context)

- Consensus "second opinion" panel (`d8a2de3`) + streaming/tts fixes (`3a34e09`)
- P0-B judge leakage filter, reviewed turns + strictness dial (`dbddafa`)
- P0-A attempt-first gate, judge-enforced (`96f1849`)
- P1 retrieval micro-quiz on due tiles (`8fb4131`)
- P1 prerequisite-DAG skill map (`46b5ddd`)
- CI: ruff format + private-clone auth/pin (`bb86593`, `b41eb25`)
- P2 quick-reply Socratic buttons + generalized UNICORN RULE (`a8a2dd2`)
