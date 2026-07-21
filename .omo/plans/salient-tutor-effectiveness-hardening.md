# salient-tutor-effectiveness-hardening - Work Plan

## TL;DR (For humans)
<!-- Filled last after the detailed plan was completed. -->

**What you'll get:** An installable, secure tutor release whose browser and CLI both run the same durable lesson loop, enforce real Apply-level and delayed-retrieval mastery, and preserve attempts/reviews/cards safely. It will also ship deterministic learning-effectiveness reports, an opt-in live smoke, and documentation that matches reality.

**Why this approach:** Release packaging and trust boundaries are fixed first, then the server-owned learning state machine becomes the only path that can advance mastery. Tests use fake models by default and real browsers/isolated wheels for proof, so feature presence is not mistaken for learning effectiveness.

**What it will NOT do:** It will not add multi-user hosting, replace the current frameworks/kernel/scheduler, redesign unrelated UI, complete unrelated mnemonic work, or publish the external kernel without separate authorization. Paid provider calls and secrets stay out of default CI and evidence.

**Effort:** XL
**Risk:** High - this changes packaging, security boundaries, persistence schema, browser orchestration, and mastery semantics, with an external kernel release prerequisite.
**Decisions to sanity-check:** `salient-core==0.7.6` must already be published; non-loopback mode requires HTTPS plus bearer authentication; SM-2/KG review state is authoritative; legacy unverifiable durable mastery is downgraded during migration.

Your next move: start work with `$start-work` after confirming the external kernel prerequisite, or request a high-accuracy plan review first.

---

> TL;DR (machine): XL/high-risk remediation: package the release, secure boundaries, unify durable browser/CLI learning, enforce evidence-backed mastery, harden persistence/async work, add outcome evaluation, and update handoff documentation.

## Scope
### Must have
- A wheel/sdist that contains prompts, curricula, pedagogy data, HTML, JavaScript, CSS, fonts, and vendored browser dependencies, and runs without a source checkout.
- An immutable `salient-core==0.7.6` dependency after that version is verifiably available from the configured package index; CI must no longer install a mutable private `@main` branch.
- Same-origin WebSocket enforcement on loopback and bearer authentication for every HTTP/WebSocket application route when binding to a non-loopback address.
- Parser/allowlist SVG sanitization, DOM-safe rendering, no inline event handlers, SSRF-aware endpoint policy, and no API keys in URLs.
- One durable learning state machine used by browser and CLI: curriculum binding, resume/pause/abandon, server-authored assessments, attempts, reviews, cards, and analytics.
- One mastery authority derived from SM-2/KG state; Apply-level fresh-case evidence for provisional mastery; an at/after-due retrieval for durable mastery.
- Fail-safe attempt-first behavior: an unavailable or malformed pedagogy judge produces a deterministic probing question and never releases the unchecked draft.
- Atomic idempotency claims and durable outbox processing for cross-store review effects; blocking extraction offloaded from the event loop.
- Complete web-run telemetry and outcome metrics for baseline, post-test, delayed recall, transfer, hint dependence, time-to-mastery, leakage, completion, and abandonment.
- Deterministic fake-model E2E evaluation in default CI, an opt-in credentialed live smoke, and documentation aligned with the shipped release.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not replace FastAPI, SQLite, salient-core, SM-2, or the vanilla browser client with a new framework.
- Do not introduce multi-user accounts, a hosted service, billing, cloud infrastructure, or public internet deployment automation.
- Do not make paid model calls in default CI or store/log raw provider tokens, auth tokens, uploaded document contents, or learner PII in evidence artifacts.
- Do not weaken, delete, or rewrite existing passing tests merely to accommodate the new contracts; migrate assertions only when the public contract intentionally changes.
- Do not complete unrelated mnemonic/palace features, redesign the visual language, or perform repository-wide style cleanup.
- Do not duplicate runtime assets between top-level and package directories; move to one canonical packaged source.
- Do not publish `salient-core` or mutate its external repository without separate explicit authorization. If `salient-core==0.7.6` is unavailable from the configured index, Task 2 must stop with package-index evidence instead of substituting a mutable VCS dependency.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD. For every behavioral todo, first add the named pytest/Playwright regression and capture its expected failure; implement the smallest change; rerun targeted tests, then the full suite. Pure file moves use an installed-artifact test that fails before the move.
- Frameworks/tools: pytest for Python units/integration, Playwright Chromium for browser flows and security regression, `python -m build` plus isolated `uv venv`/`uv pip install` for distribution smoke, Ruff and basedpyright for changed/new Python modules, `node --check` for browser modules.
- Evidence root: outside an ulw-loop use `.omo/evidence/salient-tutor-effectiveness-hardening/`; under ulw-loop use `<attemptDir>` from `omo ulw-loop status --json`. Every task writes the exact named log/JSON/screenshot below and redacts secrets.
- Baseline commands: `.venv/bin/python -m pytest -p no:cacheprovider`, `.venv/bin/python -m ruff check src tests tools`, `.venv/bin/python -m ruff format --check src tests tools`, `node --check <every packaged JS module>`.
- No test may pass solely by checking source text. Package tests install the built wheel; browser tests drive a live server; concurrency tests use barriers/fault injection; due-time tests use an injected clock.
- CI dependencies must explicitly include `build`, basedpyright, and a pinned Playwright runner/browser revision. PR CI installs the matching Chromium and runs offline only; scheduled/manual live evaluation is a separate credential-gated workflow.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.

- Wave 1, release and trust boundary: Tasks 1, 3, and 4 run in parallel. Task 2 follows Task 1; Task 5 follows Task 3.
- Wave 2, durable backend correctness: Tasks 6, 8, 9, and 10 run in parallel. Task 7 follows Task 6.
- Wave 3, primary learner journey: Task 11 follows Tasks 1, 3, 6, and 10; Task 13 (CLI parity) can run alongside it; Task 12 follows Tasks 7, 8, and 11.
- Wave 4, proof and maintainability: Tasks 14 and 15 run in parallel after their dependencies; Task 16 follows Tasks 1-15.
- Wave 5 is the four-lane final verification wave. Do not begin it until Tasks 1-16 are complete and the worktree contains no unrelated edits.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2, 11 | 3, 4 |
| 2 | 1; external availability of `salient-core==0.7.6` | 16 | 5, 6, 8, 9, 10 |
| 3 | none | 5, 11 | 1, 4 |
| 4 | none | 15 | 1, 3 |
| 5 | 3 | 14, 15 | 2, 6, 8, 9, 10 |
| 6 | none | 7, 11, 13 | 2, 5, 8, 9, 10 |
| 7 | 6 | 12, 13, 14 | 8, 9, 10 |
| 8 | none | 12, 14 | 6, 9, 10 |
| 9 | none | 15, 16 | 6, 8, 10 |
| 10 | none | 11, 13 | 6, 8, 9 |
| 11 | 1, 3, 6, 10 | 12 | none on the same frontend files |
| 12 | 7, 8, 11 | 14, 15 | none on the same frontend files |
| 13 | 6, 7, 8, 10 | 14, 16 | 11, 12 |
| 14 | 7, 10, 12, 13 | 16 | 15 |
| 15 | 5, 9, 10, 12 | 16 | 14 |
| 16 | 1-15 | final verification | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [ ] 1. Package every runtime asset behind one resource API
  What to do / Must NOT do: Start with an installed-wheel regression that proves current `web`, prompt, and curriculum lookups fail. Move the canonical runtime content from top-level `prompts/`, `data/`, and `web/static/` into `src/salient_tutor/resources/{prompts,data,web}/`; add `resources/__init__.py` and `resource_paths.py` using `importlib.resources.files`. Add and declare `platformdirs` plus `state_paths.py` using `platformdirs.user_data_path("salient-tutor")`: new installed launches use `<user-data>/work` and `<user-data>/last-workspace`; explicit `TUTOR_WORK_ROOT` still wins; a source checkout with an existing repo pointer imports that target once into the new pointer without moving/deleting learner data. Update daemon, pedagogy, curricula, static mounts, tools, tests, README paths, and image/font lookup callers. Configure recursive package data. Delete the dead second stylesheet. Do not duplicate resources, use `cwd`/`parents[2]` fallbacks, or write under site-packages.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 2, 11
  References (executor has NO interview context - be exhaustive): `pyproject.toml:49-54`; `src/salient_tutor/daemon.py:45-48,992-1005`; `src/salient_tutor/web.py:49-55,277-280,1712-1715`; `src/salient_tutor/pedagogy.py`; `tools/transform_learning_catalog.py`; `tools/build_memory_palace.py`; `web/static/index.html:7,134-135`; active stylesheet `web/static/css/app.css`; dead stylesheet `web/static/app.css`.
  Acceptance criteria (agent-executable): Red test fails against the pre-change wheel. `python -m build --wheel --sdist` succeeds; archives contain every resource subtree; isolated wheel and sdist installs from an unrelated empty cwd and read-only venv pass `pip check`, CLI/web help, resource enumeration, runner construction, live `GET /`, state creation, restart, and workspace recovery. Neither site-packages nor source tree changes. Legacy source pointer imports once and remains intact. Resource-path grep finds no checkout-relative runtime lookup.
  QA scenarios (name the exact tool + invocation): Happy: test wheel and sdist separately in `/tmp/salient-tutor-{wheel,sdist}-qa`, chmod venv read-only after install, start from an empty cwd, exercise resources/state/restart, and save `<attemptDir>/task-1-package.log`. Failure: remove a disposable installed resource and assert typed startup failure; make user-data unwritable and assert a path-specific boundary error with no partial pointer; save the same log.
  Commit: Y | `fix(packaging): include and resolve runtime resources`

- [ ] 2. Consume an immutable released salient-core and test the installed artifact in CI
  What to do / Must NOT do: First verify `salient-core==0.7.6` is available from the configured package index using a clean resolver. If unavailable, record the resolver transcript and stop this todo; do not publish externally, fall back to a sibling checkout, or substitute a mutable branch. When available, pin exactly `salient-core==0.7.6`, remove the private-token `@main` installation, add `build` to dev tooling, and make CI build the sdist/wheel once, install the wheel into clean Python 3.11/3.12/3.13 environments, run installed-artifact smoke plus the suite, and inspect the archive manifest.
  Parallelization: Wave 1 after Task 1 | Blocked by: 1 and external package availability | Blocks: 16
  References: `pyproject.toml:8-21,24-44`; `.github/workflows/ci.yml:26-49`; `README.md:73-88`; `docs/HOWTO.md:17-41,152-161`; Task 1 distribution test.
  Acceptance criteria: `uv pip install --python <clean-python> 'salient-core==0.7.6'` resolves without Git credentials. CI contains no `SALIENT_CORE_TOKEN`, `git+`, or mutable branch install. All three Python versions install the built wheel, execute CLI/web smoke and 428+ tests, and archive the wheel-content listing. Dependency resolution fails closed if 0.7.6 is removed from the index fixture.
  QA scenarios: Happy: reproduce the CI install/test sequence locally in a disposable venv and save `<attemptDir>/task-2-installed-ci.log`. Failure: point `UV_INDEX_URL` at an empty local index and confirm dependency resolution fails before tests, with no VCS fallback; save `<attemptDir>/task-2-resolution-failure.log`.
  Commit: Y | `build(release): pin kernel and test installed distributions`

- [ ] 3. Enforce same-origin WebSockets and authenticated non-loopback serving
  What to do / Must NOT do: Add `security.py` with a frozen parsed `SecurityConfig` covering REST, SSE, static app, and WebSocket upgrade. Default host remains `127.0.0.1`. `TUTOR_PUBLIC_ORIGIN`/`TUTOR_ALLOWED_ORIGINS` are canonical parsed origins; never derive trust from a request `Host`. Reject missing/null/unlisted browser origins before `ws.accept()`. Refuse non-loopback startup unless `TUTOR_AUTH_TOKEN` is set and transport is HTTPS via uvicorn certificate/key or `TUTOR_TRUSTED_TLS_PROXY=1` with an HTTPS public origin. In non-loopback mode require bearer auth for HTTP/SSE and a token-bearing WS subprotocol. Browser token arrives only in URL fragment, moves to sessionStorage, and the fragment is removed; never use query strings/localStorage/logs. Rejected requests must not instantiate/start a runner.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 5, 11
  References: `src/salient_tutor/web.py:152-153,283-299,1716-1733`; `web/static/js/tutor.js` WebSocket construction and fetch call sites; `tests/test_config_api.py`; security finding at `src/salient_tutor/web.py:423-501`.
  Acceptance criteria: Automated matrix covers IPv4/IPv6 loopback, configured HTTPS origin, hostile/forged/missing/null Origin, REST/SSE/WS, missing/wrong/correct credentials, plaintext exposed bind refusal, direct TLS, and trusted-proxy mode. Wrong cases return 401/403 or WS 1008 before daemon work; correct cases work; logs/HAR contain no token. Existing loopback tests remain credential-free.
  QA scenarios: Happy: Playwright opens `http://127.0.0.1:<port>/#token=<redacted>` against authenticated non-loopback-config mode, loads config and establishes WS; save redacted HAR and `<attemptDir>/task-3-auth.png`. Failure: a Playwright page served from a second origin attempts the localhost WebSocket and observes rejection with zero prompt submissions; save `<attemptDir>/task-3-cross-site.log`.
  Commit: Y | `fix(security): protect websocket and exposed routes`

- [ ] 4. Eliminate SVG and DOM injection at both rendering boundaries
  What to do / Must NOT do: Replace regex SVG cleanup with XML parsing and a strict allowlist of required SVG elements/attributes; remove `script`, `foreignObject`, external resource elements, event attributes, unsafe namespaces, CSS URL loads, and any `href`/`xlink:href` not a local fragment or explicit HTTPS link. Render sanitized SVG via parsed DOM/`replaceChildren`, not raw response `innerHTML`. Replace attribute-context templates and inline `onclick` throughout study, model, config, and card rendering with `textContent`, `.value`, `setAttribute`, and `addEventListener`. Vendor and license-pin Mermaid under packaged resources so CSP can use `script-src 'self'`; add restrictive CSP/security headers without `unsafe-inline` for scripts.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 15
  References: `src/salient_tutor/diagrams.py:90-132,186`; `web/static/js/tutor.js:16-17,168-178,508,941,1381-1402,1682-1688,1863-1880`; `web/static/index.html:134`; `tests/test_diagram_api.py:65-77`.
  Acceptance criteria: Actual Graphviz output from `URL="javascript:..."`, SVG with `foreignObject`, data/external URLs, CSS URLs, event handlers, and namespace tricks is removed/rejected; valid Mermaid/Graphviz/D2 output still renders. A filename `x\" onpointerenter=\"...` remains literal text and creates no handler attribute. CSP blocks inline script in Playwright with no application console errors.
  QA scenarios: Happy: Playwright renders one valid diagram and a quoted/unicode filename; save `<attemptDir>/task-4-safe-render.png`. Failure: submit every malicious fixture and assert `window.__xss` remains undefined, unsafe selectors/attributes are absent, and CSP reports the block; save DOM/console evidence to `<attemptDir>/task-4-xss.json`.
  Commit: Y | `fix(security): harden svg and dom rendering`

- [ ] 5. Move model probes to typed POST bodies and enforce endpoint policy
  What to do / Must NOT do: Add strict Pydantic request models for embed/librarian/LMS probe/load routes. Replace key-bearing GETs with authenticated POST JSON. Create one endpoint parser that allows only HTTP(S), rejects userinfo/fragments/malformed ports, disables redirects, resolves and rechecks DNS at connection time, and blocks link-local/metadata/reserved destinations always; in non-loopback mode also block loopback/private destinations unless explicitly listed in `TUTOR_MODEL_ENDPOINT_ALLOWLIST`. Preserve intentional loopback/private LM Studio access only for loopback tutor mode. Persist any explicitly saved raw key atomically in owner-only `0600` state files (or store an environment-variable reference), return only masks, and redact upstream bodies/errors.
  Parallelization: Wave 1 | Blocked by: 3 | Blocks: 15
  References: `src/salient_tutor/web.py:1223-1294,1296-1387,1522-1639`; `web/static/js/tutor.js:1728-1790,1835-1935`; `pyproject.toml:14-21`; related API tests `tests/test_embed_config_api.py`, `tests/test_librarian_config_api.py`, `tests/test_lms_api.py`.
  Acceptance criteria: Existing configured local endpoints still probe on loopback. Off-loopback tests reject `file:`, userinfo, redirects, DNS rebinding fixture, `127.0.0.1`, RFC1918, link-local, and IPv6 local forms unless explicitly allowlisted. Server access logs and Playwright HAR contain no `api_key=`. Malformed requests are 422; denied targets are 400/403 with a typed safe error.
  QA scenarios: Happy: local fake LM Studio returns models through POST and the UI displays them; save `<attemptDir>/task-5-local-model.log`. Failure: attempt metadata-service/private targets in exposed mode and verify the fake target receives zero requests; save `<attemptDir>/task-5-ssrf.json`.
  Commit: Y | `fix(security): validate model endpoints and secret transport`

- [ ] 6. Establish one mastery snapshot contract and migrate persisted state
  What to do / Must NOT do: Add schema v3 with explicit mastery evidence: assessment items carry `is_fresh_case` and stable `case_id`; sessions retain a cached stage only for migration/read performance; review applications persist the scheduler's prior due time, applied time, and resulting due time. Introduce a typed `MasterySnapshot` assembled by the daemon from assessment evidence plus authoritative SM-2/KG review state. Remove direct independent mastery-stage assignments from `LessonController`; session, curriculum, skill-map, and analytics responses must all use the same snapshot builder. Migrate v2 rows conservatively: existing `durable_mastery` becomes `provisional_mastery` unless an at/after-due passing review can be proven.
  Parallelization: Wave 2 | Blocked by: none | Blocks: 7, 11, 13
  References: `src/salient_tutor/lesson_store.py:10,52-194,494-514,578-607`; `src/salient_tutor/lesson.py:200-220`; `src/salient_tutor/daemon.py:1475-1537,1658-1662,2005-2021,2138-2157`; `tests/test_lesson_store.py:218-250`; `NEXT_STEPS_PR23.local.md:25-27`.
  Acceptance criteria: Given identical persisted evidence, `/api/sessions`, curricula, skill-map, and analytics return the same stage. Immediate passes cannot yield durable mastery. v2 migration preserves attempts/reviews/cards, is idempotent, backs up before destructive table changes, and produces a report listing applied migration and downgraded unverifiable rows.
  QA scenarios: Happy: migrate a fixture containing unstarted/provisional/proven durable examples and compare all four API views; save `<attemptDir>/task-6-mastery-migration.json`. Failure: inject a migration failure mid-transaction, verify original DB and backup remain usable and rerun succeeds; save `<attemptDir>/task-6-migration-failure.log`.
  Commit: Y | `feat(mastery): unify evidence and persisted stages`

- [ ] 7. Enforce Apply-level fresh-case, delayed-retrieval, and fail-safe Socratic gates
  What to do / Must NOT do: Make item generation, Bloom level, rubric, reference evidence/answer, `case_id`, `is_fresh_case`, and judge verdict server-owned; remove `judge_result` from `AttemptRequest` and reject unknown mastery/scoring fields. Define fresh mechanically as a normalized case/source fingerprint absent from teaching examples and all prior attempts for the skill. Require every rubric criterion and scorer confidence >=0.80 for an Apply pass. Completion rejects missing evidence. Award durable mastery only when a different fresh case passes at/after `eligible_due_at`; early reviews remain practice. Phase-aware fail-safe policy: in `awaiting_attempt`/assessment phases, judge missing/timeout/exception/malformed returns exactly `Try this first: explain how you would apply <topic> in a new example.` with topic safely derived from session state and none of the draft; in `model`/explanation phases teaching may continue but creates no mastery evidence; unbound legacy chat cannot claim mastery.
  Parallelization: Wave 2 after Task 6 | Blocked by: 6 | Blocks: 12, 13, 14
  References: `README.md:35-42`; `prompts/tutor.md:26-33,69-105`; `src/salient_tutor/lesson.py:101-118,134-153,253-319`; `src/salient_tutor/daemon.py:1409-1471,1674-1738`; `tests/test_lesson_store.py:108-179`; `tests/test_quiz_review.py:122-135`.
  Acceptance criteria: Tests prove forged `judge_result`/Bloom/rubric/provenance is rejected, literal skill-ID and replayed teaching examples do not pass, Apply fresh-case pass is provisional, before/exactly-at/after-due behavior is correct, wrong topic/stale due/partial/unscored/hinted cases do not create durable mastery, and completion before evidence is 409. Judge absent/timeout/exception/malformed has the identical phase-aware fail-safe; raw draft never reaches stream, done, history, or logs in attempt-required phases and model-phase explanation does not loop.
  QA scenarios: Happy: drive diagnose through model, Apply, completed, and clock-advanced delayed retrieval with fake tutor and independent fake scorer; save `<attemptDir>/task-7-mastery-flow.json`. Failure: forged client scoring, phase skip, same-case replay, early review, wrong topic, judge failure modes, and answer-bearing draft; save `<attemptDir>/task-7-gate-rejections.json`.
  Commit: Y | `feat(pedagogy): enforce evidence-backed mastery gates`

- [ ] 8. Make attempts and scheduler review effects crash-safe and idempotent
  What to do / Must NOT do: Replace read-then-write with atomic store APIs. Claim each idempotency key together with a canonical request hash; same key/same payload replays the stored response, same key/different payload raises `IdempotencyConflict` mapped to 409. One `BEGIN IMMEDIATE` transaction inserts attempt, event, phase transition, and mastery evidence. Add `review_outbox` with pending/processing/applied/failed, attempt/review identity, request hash, retry count, and exact response. Claim before KG/SM-2, mark applied afterward, and reconcile pending/processing rows on startup. Before implementation, verify `salient-core==0.7.6` accepts an idempotency identity for scheduler/KG review; if not, stop with an interface test because exactly-once external application cannot be guaranteed in this repo. Never hold SQLite open across model/network work.
  Parallelization: Wave 2 | Blocked by: none | Blocks: 12, 14
  References: `src/salient_tutor/lesson.py:161-220`; `src/salient_tutor/lesson_store.py:216-304,379-403,622-626`; `src/salient_tutor/daemon.py:1597-1630`; `tests/test_lesson_store.py:46-106`; `NEXT_STEPS_PR23.local.md:35-37`.
  Acceptance criteria: Barrier-controlled same-key/same-payload concurrency produces one effect and deterministic replay; same-key/different-payload is 409; distinct keys create legitimate retries. Fault injection at every boundary leaves no effect or a recoverable outbox row; restart applies exactly once. A released-kernel contract test proves duplicate outbox delivery with the same identity produces one KG/scheduler mutation.
  QA scenarios: Happy: run 20 concurrent duplicate requests and assert row/effect counts are one; save `<attemptDir>/task-8-concurrency.json`. Failure: parameterize crashes at claim/attempt/event/transition/scheduler/mark-applied boundaries, restart, drain, and verify final consistency; save `<attemptDir>/task-8-crash-matrix.log`.
  Commit: Y | `fix(storage): make learning side effects atomic`

- [ ] 9. Offload extraction and own every background task structurally
  What to do / Must NOT do: Move complete synchronous text extraction/OCR/file work behind `anyio.to_thread.run_sync` and a capacity limiter. Add persisted extraction jobs keyed by full `(project_id, document_sha)` with pending/running/succeeded/failed state and one single-flight task: POST starts/returns that job; every SSE client observes/replays its progress; disconnect never cancels shared work; reconnect/restart resumes or deterministically marks interrupted work retryable; KG ingestion is idempotent by job/document identity. Replace unowned WebSocket waiters, runner stops, and probe tasks touched here with task groups/registries that remove completed tasks, capture exceptions, and await shutdown.
  Parallelization: Wave 2 | Blocked by: none | Blocks: 15, 16
  References: `src/salient_tutor/daemon.py:893-895,941-957,1168-1188,1269-1289,2239-2280`; `src/salient_tutor/study.py:336-422`; `src/salient_tutor/web.py:326-414,504-527,1127-1200,1450-1490`; `tests/test_study_upload_api.py:473-530`.
  Acceptance criteria: With fake OCR blocked, config/heartbeat/light request completes within one second. Concurrent POST plus multiple SSE clients/reconnects for one SHA invokes extraction, model parsing, and KG ingest once and returns the same terminal job. Restart behavior is deterministic; cancellation leaves no live task/unhandled exception; capacity is enforced. No arbitrary sleeps.
  QA scenarios: Happy: start one POST and three extraction streams, disconnect/reconnect one, observe shared progress plus responsiveness, and save `<attemptDir>/task-9-responsiveness.json`. Failure: kill/restart during OCR and force subprocess/model/KG failure; verify one retryable/failed job and no duplicate fact ingestion in `<attemptDir>/task-9-cancellation.log`.
  Commit: Y | `fix(async): isolate extraction and own background tasks`

- [ ] 10. Route CLI, HTTP, and WebSocket turns through one telemetry-aware submission seam
  What to do / Must NOT do: Add a typed daemon submission service with blocking and streaming adapters. It owns runner selection/start, session-state injection, agent-run creation/finalization, output hash, error recording, and event filtering. Make CLI `_run`, `/api/prompt`, `/ws/tutor`, quiz/grading, and delegated tutor work call that seam rather than direct `runner.submit`. Preserve streaming event order and never persist prompt/reply bodies in `agent_runs`; only hashes, status, timing, model, request type, and session ID.
  Parallelization: Wave 2 | Blocked by: none | Blocks: 11, 13
  References: `src/salient_tutor/cli.py:44-76`; `src/salient_tutor/web.py:315-405,451-515,530-540`; `src/salient_tutor/daemon.py:1269-1345,1674-1738`; `src/salient_tutor/lesson_store.py:142-155,545-607`; `tests/test_codex_runner.py`; `tests/test_session_api.py`; `NEXT_STEPS_PR23.local.md:28-30`.
  Acceptance criteria: Identical fake runner turns through CLI, HTTP, and WS produce the same submission contract and one finalized `agent_runs` row each with the correct session/request type. Success, runner error, timeout, cancellation, and client disconnect all finalize status once. Existing streaming kinds/order and sentinel behavior remain compatible.
  QA scenarios: Happy: run one fake-model turn through all three entry points and compare normalized results/analytics in `<attemptDir>/task-10-submission-parity.json`. Failure: force timeout and disconnect; assert no `running` rows or raw content remains, saving `<attemptDir>/task-10-finalization.log`.
  Commit: Y | `refactor(runtime): unify prompt submission and telemetry`

- [ ] 11. Make durable session selection and recovery the default Coach experience
  What to do / Must NOT do: Convert the packaged browser script to ES modules with a central `api.js` and `session-store.js`. On startup fetch current session: resume an active session after confirmation-free reload, show paused session controls, or present curriculum/custom/study bindings when no session exists. Replace hard-coded curriculum prompts with `/api/curricula/list`; selecting a topic creates a bound session, attaches it to WS, persists only the session ID in sessionStorage, and renders phase/status. Add pause/resume/abandon/new controls with optimistic version and 409 refresh. Free chat must explicitly create a `custom:` session before sending; do not retain a parallel unbound path.
  Parallelization: Wave 3 | Blocked by: 1, 3, 6, 10 | Blocks: 12
  References: `src/salient_tutor/web.py:423-437,558-711,1095-1102`; `src/salient_tutor/lesson.py:41-118`; `web/static/js/tutor.js:657-679,1319-1370,1974-2005`; `web/static/index.html:35-119`; `tests/test_session_api.py:9-53`.
  Acceptance criteria: Playwright proves curriculum, study, and custom starts create canonical session bindings; reload resumes the exact session and pending phase; pause/resume/abandon reflect server versions; stale version refreshes rather than losing work; every WS prompt contains/uses the attached session ID. `rg 'const CURRICULUM' packaged-resource-path` returns no hard-coded catalog.
  QA scenarios: Happy: choose a curriculum topic, reload mid-phase, resume, then abandon/start custom; save trace and `<attemptDir>/task-11-session-recovery.png`. Failure: delete the attached session server-side and submit; client shows conflict, clears stale ID, and offers recovery without sending an unbound prompt; save `<attemptDir>/task-11-stale-session.json`.
  Commit: Y | `feat(web): make durable sessions the primary flow`

- [ ] 12. Drive assessments, remediation, reviews, cards, and progress from session state
  What to do / Must NOT do: Add dedicated `assessment.js` and `learning-progress.js` modules. When phase requires an item, fetch/issue the server-owned item, render only learner-safe fields, submit answer with a generated idempotency key and hint count, display criterion-specific feedback, and branch to remediation or next phase based solely on returned session state. Apply the scheduler review through `/reviews`, surface next due/durable status, create/list/retire tutor cards, and refresh progress/retention/analytics. Prevent generic chat or “got it” from advancing phases. Preserve keyboard/accessibility semantics and never place reference answers in DOM, data attributes, logs, or storage.
  Parallelization: Wave 3 after Task 11 | Blocked by: 7, 8, 11 | Blocks: 14, 15
  References: `src/salient_tutor/web.py:603-710`; `src/salient_tutor/lesson.py:120-319`; `src/salient_tutor/daemon.py:1597-1662`; `web/static/index.html:52-89,94-119`; `web/static/js/tutor.js:1010-1140,1280-1370`; `tests/test_session_api.py`; `tests/test_lesson_store.py:23-218`.
  Acceptance criteria: Real-browser deterministic flow covers wrong answer/remediation, hint use, pass, review application, card creation/retirement, phase completion, and later due review. The UI never displays a reference answer before submission; duplicate clicks/reconnects create one attempt/review. Progress and retention match API mastery snapshot after every transition. Keyboard-only flow and accessible names pass Playwright assertions.
  QA scenarios: Happy: complete a full fake-model lesson plus clock-advanced delayed review and save trace/screenshots to `<attemptDir>/task-12-learning-flow.zip`. Failure: rapid double-submit, offline/reconnect, stale version, unscored judge, and early review all remain recoverable without false mastery; save `<attemptDir>/task-12-failure-matrix.json`.
  Commit: Y | `feat(web): integrate assessment and spaced review loop`

- [ ] 13. Expose the same durable session lifecycle through the CLI
  What to do / Must NOT do: Extend the existing argparse CLI without breaking the one-shot message path. Add explicit subcommands `session start`, `session status`, `session pause`, `session resume`, `session abandon`, `session advance`, `assessment issue`, `assessment submit`, `review apply`, and `cards list`; each accepts `--work-root` and the relevant session/version/idempotency fields, uses the same daemon controller and submission seam as web, and emits stable machine-readable JSON with nonzero exit codes for 4xx/409 conflicts. `salient-tutor MESSAGE --new-session` remains a compatibility shortcut that creates/attaches a session before the turn. Do not duplicate scoring, mastery, or scheduler logic in CLI handlers.
  Parallelization: Wave 3 | Blocked by: 6, 7, 8, 10 | Blocks: 14, 16 | Can parallelize with: 11, 12
  References: `src/salient_tutor/cli.py:1-80`; `src/salient_tutor/daemon.py:1539-1662`; `src/salient_tutor/web.py:558-711`; `tests/test_session_api.py`; `tests/test_lesson_store.py:23-218`.
  Acceptance criteria: A CLI-created session is visible/resumable in the web API and vice versa. Structured submit enforces server-owned item/version, idempotency, mastery gates, and 409 stale-version behavior. `--help` documents every subcommand; JSON output has stable keys; invalid/missing IDs and wrong state return clear stderr plus exit 2/4xx without mutating state. One-shot compatibility tests remain green.
  QA scenarios: Happy: create a curriculum session, issue/submit an Apply item, pause/resume, and list cards from a clean CLI; then fetch the same session over HTTP, saving `<attemptDir>/task-13-cli-parity.json`. Failure: duplicate submit, forged judge fields, stale version, early review, and unknown session each produce deterministic errors and zero duplicate side effects in `<attemptDir>/task-13-cli-failures.log`.
  Commit: Y | `feat(cli): expose durable lesson lifecycle`

- [ ] 14. Add outcome metrics and reproducible effectiveness evaluation
  What to do / Must NOT do: Add typed analytics for baseline accuracy, immediate post-test, at/after-due delayed recall, fresh-case transfer, hints per pass, time-to-provisional/durable mastery, leakage decisions, completion/abandonment, and relearning after lapse. Correct “recall at due” to require `reviewed_at >= prior_due`. Commit a versioned fixture corpus, seed, model/version fields, primary metrics, denominators, and explicit pass thresholds (zero answer leakage, zero forged/early durable mastery, deterministic transfer/retention thresholds recorded in the report). Create deterministic evaluation fixtures and an E2E runner using fake tutor/judge transcripts for leakage, remediation, restart, mastery refusal, early review, delayed review, and transfer. Add a two-run delayed-retention protocol that persists cohort/session/due-time state and resumes after due; an immediate smoke is never labeled retention evidence. Add an opt-in `scripts/smoke_learning_loop.py` that requires explicit `--allow-paid` plus provider credentials, redacts content/secrets, and never runs in default CI.
  Parallelization: Wave 4 | Blocked by: 7, 10, 12, 13 | Blocks: 16
  References: `src/salient_tutor/lesson_store.py:545-607`; `src/salient_tutor/reviewlog.py`; `tests/test_quiz_review.py:94-135`; `docs/TODO.md:15-20`; `docs/design-research.md:24-37`; existing `scripts/smoke_judge_deepseek.py` for opt-in conventions only.
  Acceptance criteria: Frozen-clock fixtures compute every metric with explicit numerators/denominators and exclude early reviews from due recall. The report records thresholds, seed, fixture/model versions, and pass/fail per primary outcome. Deterministic E2E runs offline and fails if answer leakage, phase bypass, false durable mastery, or telemetry omission is reintroduced. A delayed run resumes the same cohort after due and computes retention separately from immediate performance. Live smoke exits without a call unless both credential and `--allow-paid` are present; with a fake provider it produces a redacted JSON report matching schema.
  QA scenarios: Happy: run offline eval twice with the same seed and byte-compare normalized reports; save `<attemptDir>/task-14-eval-report.json`. Failure: inject a leaking tutor, early review, generous low-confidence judge, and zero-token response; runner must fail each named criterion in `<attemptDir>/task-14-eval-failures.log`.
  Commit: Y | `feat(evaluation): measure learning outcomes and safeguards`

- [ ] 15. Consolidate touched domains into bounded typed modules without changing contracts
  What to do / Must NOT do: After behavioral tests are green, move touched code into cohesive modules: `resource_paths.py`; `security.py`; `submission.py`; `mastery.py`; `routes/{sessions,study,config,media}.py`; and browser `api.js`, `chat.js`, `sessions.js`, `assessment.js`, `render.js`, `library.js`, `settings.js`. Keep `TutorDaemon` as composition/lifecycle facade and `web.py` as app/lifespan/router assembly. Add strict basedpyright coverage for every new module and strict Pydantic models at changed HTTP boundaries. New modules must stay at or below 250 pure LOC; do not split by arbitrary line count or refactor untouched illustration/export logic.
  Parallelization: Wave 4 | Blocked by: 5, 9, 10, 12, 13 | Blocks: 16
  References: current sizes/responsibilities in `src/salient_tutor/daemon.py`, `src/salient_tutor/web.py`, `web/static/js/tutor.js`; raw request models `src/salient_tutor/web.py:156-230,969-990,1104-1136,1223-1665`; `pyproject.toml:56-69`.
  Acceptance criteria: Public imports/routes/JSON schemas remain compatible except intentional security method/status changes. `daemon.py`, `web.py`, and the browser entry module contain composition only for extracted domains; all new Python modules pass basedpyright strict and Ruff; all new JS modules pass `node --check`; no circular import or duplicate implementation is present. Full tests/evals/browser suite remain green after each extraction commit.
  QA scenarios: Happy: run contract snapshot comparison before/after refactor plus full gates, saving `<attemptDir>/task-15-contract-parity.json`. Failure: import every new module in randomized order and start/shutdown the app twice to expose cycles/global-state leaks; save `<attemptDir>/task-15-import-startup.log`.
  Commit: Y | `refactor(core): separate learning and web domains`

- [ ] 16. Align documentation, backlog, and release evidence with the finished product
  What to do / Must NOT do: Update README, HOWTO, CHANGELOG, project structure, environment/auth instructions, installed-wheel quick start, Codex/provider language, durable session/card/analytics workflow, outcome metric definitions, live-smoke opt-in, and troubleshooting. Remove resolved/stale TODOs and retain only verified remaining work with dates/evidence. Document loopback versus authenticated non-loopback deployment, token fragment handling, endpoint allowlists, backups/migrations, and the authoritative mastery definition. Add a release checklist that links installed-artifact, security, browser, evaluation, and live-smoke evidence; do not claim live effectiveness unless the credentialed smoke report exists.
  Parallelization: Wave 4 final | Blocked by: 1-15 | Blocks: final verification
  References: `README.md:73-88,128-161,273-283`; `docs/HOWTO.md:10-55,103-117,152-176`; `docs/TODO.md`; `CHANGELOG.md`; `.github/workflows/ci.yml`; all evidence contracts in this plan.
  Acceptance criteria: Every documented command succeeds from a clean wheel install. `rg` finds no private-token CI instructions, mutable core branch, stale test count, Claude-only runner claim, nonexistent roadmap link, query-string key example, or claim that prompt text alone enforces mastery. Documentation names limitations and distinguishes deterministic evaluation from credentialed live evidence.
  QA scenarios: Happy: execute every fenced install/start/verify command in an isolated temp directory and save `<attemptDir>/task-16-doc-commands.log`. Failure: docs checker rejects known stale phrases/links and a release checklist without required evidence; save `<attemptDir>/task-16-doc-lint.log`.
  Commit: Y | `docs(release): document durable secure learning workflow`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit: independently read Tasks 1-16 and the diff; verify every acceptance criterion has a command/evidence artifact, no Must-NOT-Have violation exists, and the external `salient-core==0.7.6` prerequisite is either proven by clean-index install or explicitly blocked with the resolver log. Evidence: `.omo/evidence/salient-tutor-effectiveness-hardening/final-compliance.md`.
- [ ] F2. Code quality/security review: run Ruff, basedpyright, `node --check`, dependency audit, inspect transaction boundaries, request models, auth/origin middleware, and sanitized DOM sinks; reject any new `Any`, broad catch, unchecked task, raw `innerHTML`, query-string secret, or mutable dependency. Evidence: `.omo/evidence/salient-tutor-effectiveness-hardening/final-quality-security.md`.
- [ ] F3. Real manual QA: install the wheel into a clean venv from an unrelated cwd, start the installed web server, drive Chromium through curriculum → session → assessment → remediation → card → reload → delayed review, exercise CLI parity, malicious origin/SVG/filename/SSRF cases, extraction reconnect, and no-credential fallback. Evidence: `.omo/evidence/salient-tutor-effectiveness-hardening/final-manual-qa/` with redacted trace, screenshots, HAR, and command logs.
- [ ] F4. Scope fidelity: compare changed paths to Scope IN/OUT and baseline `git status`; verify no external salient-core publication, secrets, unrelated visual redesign, deleted tests, or duplicate assets. Evidence: `.omo/evidence/salient-tutor-effectiveness-hardening/final-scope.md`.

Each lane must return PASS/FAIL with cited evidence; a timeout, missing artifact, or “looks good” assertion is not approval. Any failure reopens the relevant todo and requires a fresh verification run after correction.

## Commit strategy

- One commit per todo, in dependency order, using the exact Conventional Commit subject in each todo. Never combine unrelated waves or squash away the red-test evidence before review.
- Keep resource relocation/package changes separate from core pin/CI changes; keep security fixes separate by trust boundary; keep schema migrations paired with their rollback/migration tests; keep browser module extraction after behavioral parity.
- Before every commit run the todo’s targeted tests and `git diff --check`; before handoff run the full baseline gates and `git status --short`. Do not commit evidence artifacts, credentials, built wheels, venvs, HARs, screenshots, or temporary databases.
- If Task 2 is blocked because `salient-core==0.7.6` is not published, commit Tasks 1 and independent security/backend work only if their tests do not import the missing distribution; report the exact external prerequisite and do not silently alter the selected dependency strategy.

## Success criteria

- A clean isolated wheel and sdist install from an unrelated directory, with no sibling checkout, passes `pip check`, CLI/web startup, resource loading, and all automated tests; site-packages and source tree remain unwritten at runtime.
- CI installs an immutable released `salient-core==0.7.6`, builds/tests the installed artifact on Python 3.11-3.13, runs offline browser/security/evaluation lanes, and performs no paid calls or secret-bearing URLs.
- Every browser/CLI learning turn has one durable session; server-owned assessment, Apply/fresh-case evidence, delayed due-time retrieval, atomic idempotency, and one mastery snapshot govern all progress views.
- Judge failure never leaks an answer during required-attempt phases; forged client scoring, replay, early review, stale writes, cross-site WS, unsafe SVG/DOM, forbidden SSRF, and query-string keys are rejected with tests.
- Extraction and background tasks remain responsive, single-flight, restartable, cancellable, and observable without unhandled exceptions.
- Deterministic evaluation reports stable denominators and thresholds for leakage, transfer, delayed recall, hints, mastery timing, completion, and abandonment; live claims are clearly separated and credential-gated.
- README/HOWTO/CHANGELOG/TODO and release evidence describe the actual installed, secure, session-based product, and all final verification lanes approve.
