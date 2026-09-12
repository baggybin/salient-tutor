# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-12

Third public snapshot. New curricula, a codex policy gate, a provider-agnostic
coach, server-owned assessment scoring, and security hardening of the daemon.

### Added
- **Curricula**: AI Foundations, Neuroscience Fundamentals, Modern Red & Purple
  Team, and Memory Craft (classical Chinese mnemonic techniques).
- **Server-owned assessment loop**: CHECK / ANCHOR / DRILL items are authored
  and scored server-side (free-text scoring via the judge), so the coach cannot
  advance a gate by declaring a pass; a failed CHECK re-teaches MODEL instead of
  trapping the learner in a same-item drill.

### Changed
- **Kernel-port items 1-6**: effort dial fixed on Claude (`med` -> `medium`,
  plus `xhigh`/`max`) with operator-aligned thinking budgets; the coach is now
  provider-agnostic (Anthropic server tools stripped on every non-Claude
  provider; lookups go through `ask_agent("websearch")`); the bus is
  dual-registered on both MCP namespaces; the librarian read-containment fence
  is wired as a PreToolUse hook; `kg_neighbors(entity=...)` in the prompt; codex
  model map moved to `gpt-5.6-sol/terra/luna`.
- **Codex policy gate**: the kernel policy gate now applies to codex tool calls.
- Runtime resources are included and resolved from the installed package.

### Security
- **Loopback by default**: the web server binds `127.0.0.1` (was `0.0.0.0`) --
  the API is unauthenticated and fully mutating; pass `--host 0.0.0.0` to expose
  it deliberately.
- **No credential forwarding**: inherited `ANTHROPIC_API_KEY` /
  `ANTHROPIC_AUTH_TOKEN` are stripped before a subprocess is pointed at a
  third-party endpoint (the request 401s instead of leaking the operator's key);
  `CLAUDE_CODE_OAUTH_TOKEN` is always dropped off-Anthropic.
- **Study workspace alignment**: the daemon exports its resolved work_root so
  study documents cannot split from the KG/lesson DBs by launch cwd.

## [0.1.0] - 2026-07-12

Second public snapshot, consolidating the `0.0.x` line into a first
feature-bearing release: a durable lesson loop, an additional runtime provider,
and a websearch roster agent.

### Added
- **Durable tutor lesson sessions**: lesson state persists across runs —
  tutor cards are stored, assessments are scored with review applications fed
  back into the schedule, curriculum records are bindable, and provenance
  analytics / migration reports track where facts came from.
- **Codex runtime provider**: OpenAI Codex is available as a backend provider
  alongside the Claude SDK, surfaced in the Agents tab with a probe API and
  packaging support; per-agent tool policy and turn caps carry onto the codex
  path.
- **Websearch roster agent**: the roster agent that `tutor.md` already
  delegates to for web search is now included.

### Changed
- Provider probe wired into the Agents tab; adapts to core's
  `AgentRunner` `backend_factory` seam.

### Fixed
- Correctness fixes in the durable tutor loop.
- Legacy `curriculum:prereq` edges migrate to `curriculum:inferred:`.
- Probe endpoint hardened.

## [0.0.1] - 2026-07-08

First public snapshot. A spaced-repetition Socratic teaching agent built on the
`salient-core` kernel: a 9-phase lesson loop, SM-2 skill map, Mermaid diagrams,
and method-of-loci memory palaces with opt-in diffusion illustrations.
