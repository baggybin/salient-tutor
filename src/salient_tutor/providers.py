"""Provider registry — the single source of truth for agent LLM routing.

Maps each provider (anthropic / deepseek / minimax / local / codex) to its
routing, auth, thinking, and tool policy, shared by the daemon
(``_make_options``) and the web ``🤖 Agents`` config tab. Adding a provider
later is a one-line edit here; nothing else needs to know the per-provider
rules.

Routing model: endpoint providers (deepseek/minimax/local) are rerouted via a
per-agent endpoint override (the Claude SDK's ``ANTHROPIC_BASE_URL`` env), ported
from salient-core's ``endpoint:`` block. ``anthropic`` agents use the inherited
process env (a normal API key or Max-sub OAuth). ``codex`` is not an endpoint
at all — it runs salient-core's CodexProvider backend (the OpenAI Codex
runtime) behind the same AgentRunner seam. So a tutor on Opus, a librarian
on a local LM Studio model, and a judge on Codex can all run in one daemon.

Effort dial: a low/med/high/xhigh/max selector that maps to the SDK ``effort``
(via ``sdk_effort`` — the SDK spells the middle rung ``medium``) + the
``thinking`` block. ``low`` is cheaper/faster (small or no thinking budget),
``max`` deepest reasoning. Local providers can't stream thinking blocks, so they
ignore effort and force ``{type: disabled}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Valid effort wire-values (the UI sends these; validated in web.py).
EFFORTS = ("low", "med", "high", "xhigh", "max")

# Tutor effort dial → Claude SDK EffortLevel (low|medium|high|xhigh|max).
# The SDK has no "med"; passing it through made the dial a no-op on Claude.
_SDK_EFFORT = {"low": "low", "med": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}


def sdk_effort(effort: str | None) -> str | None:
    """Map the tutor's effort dial to the Claude SDK wire value (or None to
    omit the field when the dial value is unknown)."""
    return _SDK_EFFORT.get((effort or "").strip().lower())


# Valid study-project subjects. Drives advisory model suggestions only — a
# per-agent config override always wins.
SUBJECTS = ("cyber", "biology", "other")

# Effort → max thinking tokens (for the SDK's thinking budget on providers that
# support native extended thinking). Aligned with salient's operator table
# (salient/minimax.py EFFORT_BUDGET); some models cap lower than these.
_EFFORT_BUDGET = {"low": 1024, "med": 4096, "high": 8192, "xhigh": 16384, "max": 24576}


@dataclass
class ProviderSpec:
    label: str
    # True when the agent must be rerouted at a non-Anthropic endpoint (i.e.
    # every provider except anthropic). anthropic uses the inherited env.
    needs_endpoint: bool
    default_base_url: str
    # "api_key" → ANTHROPIC_API_KEY (x-api-key); "bearer" → ANTHROPIC_AUTH_TOKEN
    # (Authorization: Bearer). Mirrors salient-core's endpoint.auth_style.
    auth_style: str
    # Whether the provider can stream Anthropic extended-thinking blocks. Local
    # proxies (LM Studio/Ollama/LiteLLM) can't — the CLI aborts with
    # "Content block is not a thinking block" — so effort is forced off there.
    supports_thinking: bool
    # Built-in tools to disable on this provider (e.g. WebSearch/WebFetch don't
    # work against non-Anthropic backends). Empty = keep the agent's defaults.
    disable_builtin_tools: tuple[str, ...] = ()
    # Conventional env var holding this provider's key when no per-agent key is
    # configured. Lets every agent auto-resolve ITS OWN provider's key instead
    # of inheriting the global ANTHROPIC_API_KEY — so Claude + DeepSeek + MiniMax
    # agents coexist. Empty = none (fall back to the inherited env, as before).
    default_key_env: str = ""
    # Routing mechanism. "sdk" = claude-agent-sdk on the inherited env
    # (anthropic); "endpoint" = ANTHROPIC_BASE_URL reroute of the SDK at an
    # Anthropic-compatible gateway; "backend" = a salient-core AgentProvider
    # backend (codex) — no endpoint fields, its own runtime, never touches
    # _make_options.
    kind: str = "endpoint"


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        label="Anthropic (Claude)",
        needs_endpoint=False,
        default_base_url="",
        auth_style="api_key",
        supports_thinking=True,
        kind="sdk",
    ),
    "deepseek": ProviderSpec(
        label="DeepSeek",
        needs_endpoint=True,
        default_base_url="https://api.deepseek.com/anthropic",
        auth_style="api_key",
        supports_thinking=False,  # DeepSeek's gateway doesn't stream thinking
        disable_builtin_tools=("WebSearch", "WebFetch"),
        default_key_env="DEEPSEEK_API_KEY",
    ),
    "minimax": ProviderSpec(
        label="MiniMax",
        needs_endpoint=True,
        default_base_url="https://api.minimax.io/anthropic",
        auth_style="bearer",
        supports_thinking=True,  # coupled: M3 adaptive, M2.x always-on
        disable_builtin_tools=("WebSearch", "WebFetch"),  # Anthropic-side server tools
        default_key_env="MINIMAX_API_KEY",  # same credential the minimax_* agents use
    ),
    "local": ProviderSpec(
        label="Local (LM Studio / Ollama)",
        needs_endpoint=True,
        default_base_url="http://ai.home:1234",
        auth_style="api_key",
        supports_thinking=False,
        disable_builtin_tools=("WebSearch", "WebFetch"),  # Anthropic-side server tools
    ),
    "codex": ProviderSpec(
        label="OpenAI Codex",
        needs_endpoint=False,  # no base_url/api_key fields — its own runtime
        default_base_url="",
        auth_style="api_key",  # unused; kept for schema stability
        supports_thinking=False,  # codex reasons via its own effort dial
        default_key_env="OPENAI_API_KEY",  # or an existing `codex login` session
        kind="backend",
    ),
}


# ── Codex model/effort mapping (kept in lockstep with salient) ─────────────
# Claude tier substring → codex model, for agents swept to codex without an
# explicit model. Codex model ids are CLI-version-gated: the 5.6 ids need a
# >=0.144 codex — the bundled openai-codex-cli-bin 0.137.0a4 rejects them, so
# point SALIENT_CODEX_BIN at a newer CLI (or bump the pin) when using these.
CODEX_MODEL_BY_TIER: tuple[tuple[str, str], ...] = (
    ("opus", "gpt-5.6-sol"),  # top reasoning
    ("fable", "gpt-5.6-sol"),  # flagship-tier, same rung as opus
    ("sonnet", "gpt-5.6-terra"),  # mid / everyday
    ("haiku", "gpt-5.6-luna"),  # fast / cheap
)
CODEX_DEFAULT_MODEL = "gpt-5.6-terra"  # unknown/absent tier → balanced fallback

# Tutor effort dial → codex model_reasoning_effort wire value.
_CODEX_EFFORT = {"low": "low", "med": "medium", "high": "high"}


def codex_model_for(explicit: str, roster_model: str) -> str:
    """The codex model for an agent: an explicit config model wins; otherwise
    map the roster's Claude tier to its codex counterpart; unknown → default."""
    if explicit.strip():
        return explicit.strip()
    m = (roster_model or "").lower()
    for tier, codex_model in CODEX_MODEL_BY_TIER:
        if tier in m:
            return codex_model
    return CODEX_DEFAULT_MODEL


def codex_effort(effort: str | None) -> str | None:
    """Map the tutor's low/med/high dial to codex reasoningEffort (or None to
    let the model default when the dial value is unknown)."""
    return _CODEX_EFFORT.get((effort or "").strip().lower())


def is_minimax(model: str) -> bool:
    """Whether `model` is a MiniMax chat model (drives the thinking coupling)."""
    m = (model or "").lower()
    return "minimax" in m or m.startswith(("m3-", "m2.")) or "/abab" in m


def _minimax_thinking(model: str, effort: str) -> dict[str, Any]:
    """Inline port of salient-core's dormant ``salient_core.minimax`` policy:
    MiniMax-M3 ↔ adaptive (effort-scaled internally); M2.x ↔ always-on enabled
    with an effort-scaled budget. Kept here because ``salient_core.minimax``
    doesn't ship in this build."""
    if is_minimax(model) and ("m3" in model.lower() or "m4" in model.lower()):
        return {"type": "adaptive"}  # the model picks; effort is advisory
    budget = _EFFORT_BUDGET.get(effort, _EFFORT_BUDGET["med"])
    return {"type": "enabled", "budget_tokens": budget}


def resolve_thinking(provider: str, effort: str, model: str | None = None) -> dict[str, Any]:
    """The SDK ``thinking`` block for an agent on `provider` at `effort`.

    - ``local`` / ``deepseek`` (non-thinking providers) → ``{type: disabled}``.
    - ``minimax`` → the coupled M3/M2.x policy.
    - ``anthropic`` → ``low`` adapts off, ``med``/``high`` enabled with a budget.
    """
    spec = PROVIDERS.get(provider)
    if spec is None or not spec.supports_thinking:
        return {"type": "disabled"}
    if provider == "minimax":
        return _minimax_thinking(model or "", effort)
    # anthropic
    if effort == "low":
        return {"type": "disabled"}  # cheapest; no extended thinking
    return {"type": "enabled", "budget_tokens": _EFFORT_BUDGET.get(effort, _EFFORT_BUDGET["med"])}


# Subject → advisory tutor model. Cyber keeps the sharper, technical model (Opus);
# biology and other domains get Fable's gentler, narrative persona. Advisory only —
# the operator's per-agent config always wins.
SUBJECT_TUTOR_MODEL: dict[str, str] = {
    "cyber": "claude-opus-4-8[1m]",
    "biology": "claude-fable-5[1m]",
    "other": "claude-fable-5[1m]",
}


def suggested_tutor_model(subject: str) -> str:
    """The advisory tutor model for a study-project subject."""
    return SUBJECT_TUTOR_MODEL.get(subject, SUBJECT_TUTOR_MODEL["cyber"])
