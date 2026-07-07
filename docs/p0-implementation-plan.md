# P0 implementation plan — enforcement layer for sense-making

> **STATUS (2026-07-03): both P0 items SHIPPED on `main`.** P0-B (judge leakage
> filter + strictness dial) landed in `dbddafa`; P0-A (attempt-first gate) landed
> in `96f1849`, **folded into the same `pedagogy_filter` judge pass** rather than
> shipped as a separate `ask_operator` inbox turn (see `daemon.py:874`,
> `_PEDAGOGY_FILTER_PROMPT`). 30 tests green. **Remaining:** the live end-to-end
> run in Sequencing step 3 (needs a live key + `TUTOR_JUDGE_MODEL`/`TUTOR_VARIANT_MODEL`).
> The prose below is the original plan, kept for context.

> Turns the two highest-leverage findings from
> [`design-research.md`](./design-research.md) into concrete work. Both reuse the
> delegation shim built for the consensus panel and the event-hub streaming
> fixed on 2026-07-02. `prompts/tutor.md` already encodes the *policy*; this adds
> the *enforcement* the research says policy alone can't achieve (students bypass
> optional scaffolding at near-zero cost — arXiv:2606.15766).

---

## P0-A — "Submit your attempt first" gate

**Goal:** for a problem-type question, the learner must commit an attempt/current
understanding before the tutor answers. The tutor responds to the *attempt*.

**Evidence:** unguided AI → cognitive offloading with zero reasoning gain;
structured submit-first reverses it (MDPI Data 2025, 3-0). Optional nudges get
bypassed → enforce (arXiv:2606.15766, 3-0).

### Design decision: enforce at the seam, not just the prompt
The prompt already says "diagnose first / productive struggle." Enforcement lives
in the **turn contract**, so the learner can't just rephrase to skip it.

### Approach (recommended): tutor-initiated required prompt via `ask_operator`
The tutor, on a problem-type question, calls `ask_operator("<one probing
question — what's your current read?>")` **instead of** answering. That files a
question on the inbox and the web layer surfaces it as a distinct "your attempt"
compose state; the answer is fed back as the next turn, which the tutor then
teaches against.

**Why the bus, not just a prompt rule:** routing through `ask_operator` (a) makes
the gate a real, observable turn boundary in the stream, (b) persists the
question in `QuestionInbox` so a page reload resumes it, and (c) is enforced by
code (the answer is required input), not model goodwill.

### Files
- **`prompts/tutor.md`** — add to LESSON LOOP §0/PRIME DIRECTIVES: "For any
  problem/exercise/'how do I' question, your FIRST move is `ask_operator` with a
  single probing question eliciting their current attempt or read. Do not teach
  until they answer. Conceptual/'what is' questions are exempt." Add a HARD NO:
  "Answer a problem-type question before the learner has committed an attempt."
- **`daemon.py`** — the `ask_operator` bus tool calls `daemon.add_question(agent,
  text)` (already implemented at `add_question` → `QuestionInbox.add`). Add a
  daemon method `pending_question(agent="tutor")` wrapping `inbox.pending_for` so
  the web layer can render the open gate.
- **`web.py`** — WS handler: when the tutor's turn ends with a pending operator
  question, emit an event `{kind:"await_attempt", text:<question>, qid}`. On the
  next learner message while a gate is open, answer the question
  (`inbox.answer(qid, text)` — verify the method name) and resubmit as the turn.
  Add `GET /api/pending` for reload recovery.
- **`tutor.js`** — handle `kind:"await_attempt"`: switch the composer to an
  "attempt" state (distinct bubble style + placeholder "your best attempt…"),
  and on send, route to the gate-answer path. Reuse the existing capture-banner
  pattern for the visual affordance.
- **`css/app.css`** — an `.attempt-*` compose state mirroring `.capture-banner`.

### Tests
- daemon: a problem-type prompt files a pending question; the follow-up answers
  it and the tutor turn sees the attempt. (Stub `prompt`/inbox, no API key.)
- web: `GET /api/pending` returns the open gate; posting an answer clears it.
- prompt-lint: the new directive + HARD NO strings are present in tutor.md.

### Risk
`ask_operator`'s existing semantics may target the *operator* (a human overseer)
rather than the *learner*. Confirm the inbox `kind`/routing — if it conflicts,
add a dedicated `kind="attempt_gate"` rather than overloading operator questions.

---

## P0-B — Judge as answer-leakage filter (+ pedagogy-strictness dial)

**Goal:** before a tutor answer reaches the learner, the `judge` agent scores
whether it leaks the full solution; if it does, it's rewritten toward the next
rung of the hint ladder.

**Evidence:** base LLMs leak 35–47% (arXiv:2505.15607, Table 1); an RL pedagogy
penalty cut leakage to 10.6% while keeping solve gains (same paper, 3-0). The
existing `judge` agent (added for consensus) is the natural home.

### Approach: reuse the delegation shim, on the OUTBOUND answer
Mirror `TutorDaemon.second_opinion`: build an `ask_agent("judge", …)` call whose
prompt is "Here is a tutor's draft reply to <learner Q>. Does it hand over the
solution the learner should derive? If yes, rewrite it to the next hint-ladder
rung (orient → narrow → worked-step) without giving the answer. Return
{leaked: bool, revised: <text>}." Gate on `judge` being configured
(`TUTOR_JUDGE_MODEL`); when absent, pass through unchanged (no regression).

- **Strictness dial:** a `pedagogy_strictness` param (Explain / Socratic /
  Bare-hints) threaded into the judge prompt — the paper's tunable λ surfaced as
  an operator control. Default Socratic.

### Where to intercept
Two options — recommend (1) for a first cut:
1. **Post-turn, pre-display** in `web.py`/daemon: after the tutor turn resolves,
   if `judge` is configured and the turn was a problem-type answer, run the
   filter and stream the revised text. Simplest; keeps the tutor prompt clean.
   Cost: one extra judge round-trip on gated turns (acceptable; it's advisory
   like consensus).
2. Prompt-level self-check (tutor calls the judge itself). Rejected for P0 —
   unenforceable (the finding is that self-policing gets bypassed).

### Files
- **`daemon.py`** — `async def pedagogy_filter(question, draft, *, strictness)`
  building the `ask_agent("judge", …)` shim call (reuse `_AskShim`), returning
  `{leaked, revised}`. Reuse the JSON-unwrap logic from `second_opinion`.
- **`prompts/judge.md`** — add a second mode: "PEDAGOGY FILTER — given a learner
  question + a tutor draft, decide if the draft leaks the solution the learner
  should derive; if so rewrite to the requested hint level. Return JSON
  {leaked, revised}." Keep it compact; align with the existing reconciliation
  persona.
- **`web.py`** — apply the filter on gated turns before the final `done`; add
  `strictness` to the prompt request model + a control in the UI.
- **`tutor.js` / `index.html` / `css`** — a strictness segmented control in the
  compose bar (Explain / Socratic / Bare hints), persisted to localStorage like
  `ttsPrefs`. Show a subtle "↩ hinted (judge)" chip when a turn was rewritten,
  so the behavior is honest/visible (finding 8).

### Tests
- daemon: a leaky draft → filter returns `leaked:true` + a revised non-answer;
  a clean hint → `leaked:false` passthrough. Stub the judge `prompt`.
- config: no `TUTOR_JUDGE_MODEL` → `pedagogy_filter` is a no-op passthrough.
- prompt-lint: judge.md contains the pedagogy-filter mode + `leaked`/`revised`.
- strictness: the param reaches the judge prompt (assert on the built args).

### Risk
Latency: the filter adds a judge round-trip. Mitigate by scoping it to
problem-type turns only (skip conceptual answers) and running it *after* the
draft has streamed, replacing only if `leaked` — so the common case is unchanged.

---

## Sequencing

1. **P0-B first** (judge filter) — smaller, fully reuses the consensus shim, and
   `judge`/streaming infra is already in place. Ship + test.
2. **P0-A** (submit-first gate) — larger (new compose state, inbox routing),
   and benefits from P0-B already exercising the `ask_agent` outbound path.
3. Verify end-to-end with `TUTOR_VARIANT_MODEL` + `TUTOR_JUDGE_MODEL` set and a
   live key: ask a problem question → gate → attempt → answer → judge rewrite
   chip. (Neither is provable from tests alone; both need a live model.)

## Explicitly deferred (P1/P2 — see design-research.md)
Retrieval quizzes from due tiles (`kg_semantic_query`→`record_review`),
prerequisite-DAG skill map (`kg_neighbors`), consensus-panel trust reframing,
verified inline citations, hybrid quick-reply Socratic buttons.
