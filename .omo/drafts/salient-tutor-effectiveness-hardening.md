---
slug: salient-tutor-effectiveness-hardening
status: complete
intent: clear
pending-action: ask whether to start work or run the optional high-accuracy plan review
approach: Fix release/installability and security first; then make the durable lesson controller the only primary web learning path; enforce evidence-backed mastery; harden persistence and runtime behavior; finish with outcome evaluation and documentation.
---

# Draft: salient-tutor-effectiveness-hardening

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
release | clean wheel contains every runtime asset and boots independently | active | pyproject.toml:53; src/salient_tutor/daemon.py:45; src/salient_tutor/web.py:49
orchestration | browser chat is bound to durable sessions, assessments, reviews, cards, and curricula | active | src/salient_tutor/web.py:558; web/static/js/tutor.js:657
pedagogy | attempt-first and Apply-level delayed mastery are enforced in code, not prompt convention | active | prompts/tutor.md:26; src/salient_tutor/lesson.py:101,134,200; src/salient_tutor/daemon.py:1440
security-reliability | local deployment resists cross-site control/XSS and long work cannot block or duplicate state | active | src/salient_tutor/web.py:283; src/salient_tutor/diagrams.py:117; src/salient_tutor/lesson.py:172; src/salient_tutor/daemon.py:2267
evaluation-handoff | effectiveness is measured with repeatable outcomes and documentation matches the shipped product | active | docs/TODO.md:15; src/salient_tutor/lesson_store.py:578

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
kernel distribution | publish and pin a released salient-core version | installed releases must resolve without a sibling checkout or mutable branch | yes, via dependency update
deployment | loopback remains the default; validate WebSocket Origin always; require authentication before non-loopback bind | preserves local ergonomics while closing localhost cross-site control and exposed-service risk | yes, configuration can evolve
test strategy | TDD for behavioral boundaries; existing tests remain intact; agent-executed manual QA for CLI/API/browser/package | user approved and failures are subtle enough to require regression locks | yes
browser architecture | split the monolithic frontend only along domains touched by this plan | reduces change collision without speculative redesign | yes
mastery authority | SM-2/KG review state is authoritative; session and curriculum views derive from it | prevents conflicting mastery claims | migration required but reversible from backup
installed state | use `platformdirs.user_data_path("salient-tutor")` for new installed defaults; preserve explicit `TUTOR_WORK_ROOT`; source checkouts import their legacy pointer once | installed packages and site-packages may be read-only | yes via explicit work-root
exposed transport | non-loopback mode requires HTTPS directly or a declared trusted TLS proxy in addition to bearer auth | bearer tokens must never cross plaintext exposed links | yes via deployment config

## Findings (cited - path:lines)

- Built wheels omit repo-level runtime assets because setuptools discovers only `src` packages (`pyproject.toml:53`); runtime lookups assume checkout-relative `prompts`, `data`, and `web/static` (`src/salient_tutor/daemon.py:45`, `src/salient_tutor/web.py:49`).
- The backend has durable APIs (`src/salient_tutor/web.py:558-711`) but the browser prompt payload has no session binding (`web/static/js/tutor.js:657-679`).
- Default assessment and phase advancement do not enforce the advertised Apply-level fresh-case mastery gate (`src/salient_tutor/lesson.py:101-118,134-153,200-220`).
- Attempt-first filtering passes unchecked drafts when the judge is unavailable or fails (`src/salient_tutor/daemon.py:1440-1471`).
- Cross-origin WebSockets, active SVG links, attribute-context escaping, unrestricted configurable endpoints, and query-string API keys create security risk (`src/salient_tutor/web.py:283,1247-1277`; `src/salient_tutor/diagrams.py:117`; `web/static/js/tutor.js:17,178,1386`).
- Attempt/review workflows cross transaction boundaries and extraction performs blocking subprocess work on the event loop (`src/salient_tutor/lesson.py:172-220`; `src/salient_tutor/daemon.py:1603-1620,2267`; `src/salient_tutor/study.py:363`).
- Source verification is strong (428 tests) but the project records no live-model or delayed-retention validation (`docs/TODO.md:15-20`).

## Decisions (with rationale)

- Sequence by risk: release packaging and security gates precede feature integration so every later browser/effectiveness test runs against a distributable, safe artifact.
- Make durable session state the single orchestration seam for CLI and web, rather than adding a second frontend-only state machine.
- A session cannot complete without a server-authored Apply-level fresh-case pass; `durable_mastery` additionally requires a later retrieval timestamp at or after the SM-2 due time.
- When the pedagogy judge is absent, times out, or returns malformed output, replace any unchecked draft with a deterministic probing question; never reveal the draft.
- Claim idempotency before side effects and use transactional/outbox boundaries for scheduler/KG effects that cannot share the SQLite transaction.
- Evaluation must include deterministic fake-model behavioral tests plus credential-gated live smoke; no paid call is required for the default CI lane.
- The browser never supplies judge verdicts, Bloom claims, rubrics, fresh-case identity, reference answers, or mastery state; all are server-owned.
- Extraction is a single logical job per project/document content hash; POST and every SSE reconnect observe that same persisted job.

## Scope IN

- Runtime asset packaging, immutable released kernel dependency, wheel/sdist install smoke.
- Durable web/CLI lesson orchestration, curriculum selection, session recovery/control, assessments, reviews, cards, analytics.
- Mastery authority, Apply-level scoring, actual due-time delayed retrieval, fail-safe attempt-first behavior.
- WebSocket Origin/auth boundary, SVG/DOM injection defense, endpoint/secret handling appropriate to local-first deployment.
- Atomic attempt/review effects, nonblocking extraction, web-run analytics, targeted modularization.
- Outcome metrics, deterministic E2E evaluation, credential-gated live smoke, README/HOWTO/TODO updates.

## Scope OUT (Must NOT have)

- No replacement of salient-core, FastAPI, SQLite, SM-2, or the existing web UI framework.
- No multi-tenant account system, cloud deployment platform, billing, or hosted service.
- No redesign of visual styling or unrelated feature work such as completing the full memory-palace roadmap.
- No paid-provider call in default CI; no secrets committed or printed.
- No broad cleanup unrelated to the changed seams; preserve existing APIs unless the plan explicitly migrates their consumers.

## Open questions

- None. User approved all recommended defaults.

## Metis receipt

- First Metis dispatch hit model capacity; replacement completed with `NOT APPROVABLE` and identified missing writable installed-state paths, TLS requirements for exposed bearer auth, client-forgeable judge fields, single-flight extraction, request-hash idempotency/kernel capability, CLI parity, and delayed-retention thresholds. All findings were incorporated into `.omo/plans/salient-tutor-effectiveness-hardening.md` before handoff.

## Approval gate
status: approved
approved-by: user
approved-scope: full remediation scope from the effectiveness review
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
