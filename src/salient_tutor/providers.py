"""Provider registry — the single source of truth for agent LLM routing.

Maps each provider (anthropic / deepseek / minimax / local) to its routing,
auth, thinking, and tool policy, shared by the daemon (``_make_options``) and
the web ``🤖 Agents`` config tab. Adding a provider later is a one-line edit
here; nothing else needs to know the per-provider rules.

Routing model: every agent that isn't on ``anthropic`` is rerouted via a
per-agent endpoint override (the Claude SDK's ``ANTHROPIC_BASE_URL`` env), ported
from salient-core's ``endpoint:`` block. ``anthropic`` agents use the inherited
process env (a normal API key or Max-sub OAuth). So a tutor on Opus, a librarian
on a local LM Studio model, and a judge on DeepSeek can all run in one daemon.

Effort dial: a low/med/high selector that maps to the SDK ``effort`` + the
``thinking`` block. ``low`` is cheaper/faster (small or no thinking budget),
``high`` deeper reasoning. Local providers can't stream thinking blocks, so they
ignore effort and force ``{type: disabled}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Valid effort wire-values (the UI sends these; validated in web.py).
EFFORTS = ("low", "med", "high")

# Valid study-project subjects. Drives advisory model suggestions only — a
# per-agent config override always wins.
SUBJECTS = ("cyber", "biology", "other")

# Effort → max thinking tokens (for the SDK's thinking budget on providers that
# support native extended thinking). Conservative budgets; the SDK also accepts
# an `effort` hint and some models cap lower than these.
_EFFORT_BUDGET = {"low": 2048, "med": 8192, "high": 24576}


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


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        label="Anthropic (Claude)",
        needs_endpoint=False,
        default_base_url="",
        auth_style="api_key",
        supports_thinking=True,
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
        default_key_env="MINIMAX_API_KEY",  # same credential the minimax_* agents use
    ),
    "local": ProviderSpec(
        label="Local (LM Studio / Ollama)",
        needs_endpoint=True,
        default_base_url="http://ai.home:1234",
        auth_style="api_key",
        supports_thinking=False,
    ),
}


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
