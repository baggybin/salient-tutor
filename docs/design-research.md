# Tutor design research — evidence-based AI learning + frontend/bus leverage

> Deep-research synthesis, 2026-07-02. 3-vote adversarial verification (23/25
> claims confirmed, 2 refuted). Sources are mostly 2025–26 preprints — treat
> effect sizes as **directional**, not settled. This doc is the "why" behind the
> prioritized work in [`p0-implementation-plan.md`](./p0-implementation-plan.md).

## Thesis

**Guide sense-making, don't give answers — and make both the guidance and the
model's fallibility visible.** The strongest, most counterintuitive finding:
*more scaffolding does not produce more learning*, because students bypass
optional nudges at near-zero social cost (arXiv:2606.15766, 3-0). The wins come
from **enforced interaction** and **structured UI**, not gentler prompting.

`prompts/tutor.md` already encodes the right *policy* (productive struggle, hint
ladder that never reaches the answer, retrieval-first, "never answer your own
Socratic question"). The gap the research exposes is **enforcement**: nothing
checks that the learner attempted before the answer, and nothing checks that the
tutor's output didn't leak the solution. That's what P0 adds.

## Key findings (each with its verification vote)

1. **Retrieval + spacing + personalization is the evidence-backed core** (not
   decoration). Only peer-reviewed learning-gains study: +15 percentile for
   engaged students (arXiv:2309.13060, 3-0; correlational, so best-case). → The
   SM-2 `learner:op` gradebook + skill-map rail + retrieval quizzes *are* the
   product.
2. **Base LLMs leak solutions 35–47%** of the time even while boosting solve
   rates (arXiv:2505.15607, Table 1, 3-0). → Never use the tutor raw; treat
   answer-leakage as a first-class metric a judge scores.
3. **An RL pedagogy penalty cut leakage to 10.6%** while keeping solve gains
   (same paper, 3-0). → A judge that penalizes leakage is a *validated*
   architecture; expose its strength as a "pedagogy strictness" control.
4. **Unguided AI → cognitive offloading with zero reasoning gain**; structured
   "submit-first" interaction reverses it (MDPI Data 2025, n=150, 3-0; +2
   corroborating studies). → No bare "ask anything" box for problems.
5. **Students bypass scaffolding cheaply**; degree of scaffolding is only weakly
   correlated with uptake (arXiv:2606.15766, 3-0). → Enforce (submit-first
   gates, judge blocking leaked answers), don't just nudge.
6. **Stream token-by-token with honest per-agent status**; absence of feedback
   reads as broken; but streaming *faster* than reading raises load for dense
   content — pace it (3-0; UIST 2025 refinement).
7. **Hybrid chat + structured UI** (cards, quick-reply Socratic choices) beats
   pure free-text (NN/g, 3-0).
8. **Calibrate trust:** cite sources, add deliberate friction at decision points,
   make uncertainty visible (CHI 2024 arXiv:2401.14484, 3-0). Explanations
   *alone* can *increase* over-reliance.
9. **CoT traces & LLM citations are post-hoc narratives** (faithfulness often
   <20%; Anthropic, Turpin NeurIPS 2023; 3-0). → Frame the consensus panel as a
   *verification signal, not proof*; verify citations against the KB before
   showing them. (Note: transparency is *insufficient alone*, not worthless —
   the "epistemic theater" claim was refuted 0-3.)
10. **KG layout should match semantics:** hierarchical DAG for prerequisites,
    force-directed for exploration, radial for centering (3-0, medium). Mermaid
    `graph TD` fits the prerequisite case natively.

## Prioritized interface ideas

| # | Idea | Evidence | Bus tool (currently unused) |
|---|------|----------|------------------------------|
| P0 | **Submit-your-attempt-first gate** before answering problem-type Qs | 4, 5 | `ask_operator` (invert: tutor blocks on learner) |
| P0 | **Judge as answer-leakage filter** on outbound answers + strictness dial | 2, 3 | `ask_agent("judge", …)` |
| P1 | Real streaming w/ per-agent status ("librarian extracting", "judge reviewing") | 6 | `event_hub` (now wired) |
| P1 | Retrieval micro-quiz from the due skill-map tile (answering = the SM-2 review) | 1 | `kg_semantic_query` → `record_review` |
| P1 | Skill-map as hierarchical prerequisite DAG (mastered/available/locked) | 10 | `kg_neighbors`, `kg_stats` |
| P2 | Consensus panel reframed as verification signal (friction + uncertainty) | 8, 9 | (UI on existing `ask_consensus`) |
| P2 | Inline KB citations, verified against the KB before display | 8, 9 | `read_evidence`, `kg_query` |
| P2 | Hybrid chat: quick-reply Socratic buttons alongside free text | 7 | — |

## "Make more use of the bus" — the gap

The app exposes all 36 bus tools via `make_bus` but drives ~6. Highest-leverage
latent tools:

- **`ask_operator`** — near-dead today; becomes the submit-first gate (P0).
- **`ask_agent`/`ask_partner`** — the tutor→librarian handoff is a *direct
  in-process call* (`daemon.py` `study_extract`), so it never appears in the
  stream and skips every bus safeguard. Routing it through `ask_agent` makes the
  collaboration visible (finding 6) and governed — same seam the consensus shim
  already proved.
- **`kg_neighbors`/`kg_semantic_query`/`kg_stats`** — prerequisite DAG + quizzes.
- **`context_*` (10 tools)** — shared working-memory scratchpad across turns.
- **`propose_lesson`/`propose_skill`** — learner-triggered "save as reusable."
- **`read_evidence`/`prior_actions`/`prior_techniques`** — cited answers + recall.

## Caveats & open questions

- Most pedagogy sources are **2025–26 preprints, several author-self-evaluated**
  with LLM-judge metrics, no replication. The +15-percentile flagship is
  **correlational** with self-selected "engaged" students.
- The corpus was **thin on exactly what the app already commits to**: no surviving
  claim compared **SM-2 vs FSRS**, little on expertise-reversal, interleaving, or
  the 2-sigma benchmark.
- **Open Q1:** move the gradebook to **FSRS**? It generally beats SM-2 on
  retention-per-review in open literature; warrants a direct eval.
- **Open Q2:** at what mastery threshold should scaffolding fade
  (worked-example → Socratic → bare problem)? Corpus supports faded scaffolding
  but gives no trigger thresholds — candidate to derive from the skill map.

## Primary sources

- arXiv:2309.13060 — Personal AI Tutor case study (+15 pct, peer-reviewed)
- arXiv:2505.15607 — answer-leakage + RL pedagogy penalty (Table 1)
- arXiv:2606.15766 — students bypass scaffolding (9 datasets, 5 deployments)
- arXiv:2605.30539 — theory-grounded dialogic scaffolding (EDF framework)
- MDPI Data 2025 (10/11/172) — structured prompting vs cognitive offloading
- arXiv:2401.14484 — six GenAI design principles (CHI 2024)
- Turpin et al. NeurIPS 2023; Anthropic "Measuring Faithfulness in CoT" — CoT is post-hoc
