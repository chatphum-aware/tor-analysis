"""Token usage -> cost in USD and THB. All arithmetic lives here in Python --
the model only ever returns raw token counts (rule #1: the LLM computes
nothing). See the plan's "Show tokens used and cost in Thai baht" section.

Pricing is keyed by (provider, model) because a bare model id is not
globally unique: the same open-weights model (e.g. a Llama checkpoint)
costs a different amount depending on which host serves it, and Anthropic
model ids are meaningless on another provider's table.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.llm.providers.base import ProviderUsage

# USD per 1M tokens. Cached from the claude-api skill's Current Models
# table (Anthropic first-party API rates) -- verify against
# https://docs.claude.com/en/docs/about-claude/pricing before relying on
# this for anything beyond a rough estimate; prices change.
PRICING_AS_OF = "2026-09-02"

_PRICE_PER_MTOK_USD: dict[tuple[str, str], tuple[float, float]] = {
    # (provider, model_id): (input, output)
    ("anthropic", "claude-fable-5"): (10.00, 50.00),
    ("anthropic", "claude-mythos-5"): (10.00, 50.00),
    ("anthropic", "claude-opus-5"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-8"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-7"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-6"): (5.00, 25.00),
    ("anthropic", "claude-sonnet-5"): (2.00, 10.00),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-5"): (1.00, 5.00),
    # Gemini bills thinking tokens at the SAME rate as regular output tokens
    # (confirmed on Google's own pricing page: "Output price (including
    # thinking tokens)" is one combined figure, not two) -- this is exactly
    # why the Gemini adapter folds thoughts_token_count into output_tokens
    # rather than reporting it separately. Promotional rate through
    # 2026-12-31; rises to $1.50/$7.50 on 2027-01-01 -- re-verify after that.
    ("gemini", "gemini-3.6-flash"): (0.75, 3.75),
}

# Prompt caching multipliers, relative to the model's input rate. Keyed by
# provider because these ratios are provider-specific pricing facts, not a
# universal law -- confirmed only for Anthropic's own pricing page. Applying
# Anthropic's ratios to another provider's cache tokens would be a guess this
# project's pricing rules forbid, so an unverified provider gets (1.0, 1.0):
# its cache tokens are priced at the plain input rate rather than an invented
# discount/markup.
_CACHE_MULTIPLIERS: dict[str, tuple[float, float]] = {
    # provider: (cache_write_multiplier, cache_read_multiplier)
    "anthropic": (1.25, 0.10),
}
_DEFAULT_CACHE_MULTIPLIERS = (1.0, 1.0)

_DEFAULT_USD_THB_RATE = 36.50
_DEFAULT_USD_THB_RATE_DATE = "2026-08-28"


# Alias, not a redefinition -- keeps every existing
# `from app.derive.pricing import Usage` import working unchanged while the
# real type lives in the provider-neutral port (see llm/providers/base.py).
Usage = ProviderUsage


@dataclass
class Cost:
    usd: float
    thb: float
    usd_thb_rate: float
    rate_source_date: str
    provider: str
    model: str
    pricing_as_of: str
    is_estimate: bool = True


def get_usd_thb_rate() -> tuple[float, str]:
    """Read the USD->THB rate from env. No live FX call by design -- avoids
    a network dependency and a new failure mode in v0.1. The rate and its
    date are always returned together and must be displayed together, so a
    stale rate is visible rather than silently wrong.
    """
    rate = float(os.environ.get("USD_THB_RATE", _DEFAULT_USD_THB_RATE))
    date = os.environ.get("USD_THB_RATE_DATE", _DEFAULT_USD_THB_RATE_DATE)
    return rate, date


def compute_cost(provider: str, model: str, usage: Usage) -> Cost | None:
    """Returns None if (provider, model) isn't in the pricing table --
    callers must surface that as "cost unknown", never guess a price (same
    principle as rule #3: no silent guessing to fill a slot). Self-hosted
    endpoints will always land here, which is correct: GPU time is a real
    cost this table cannot know.
    """
    prices = _PRICE_PER_MTOK_USD.get((provider, model))
    if prices is None:
        return None
    input_rate, output_rate = prices
    cache_write_mult, cache_read_mult = _CACHE_MULTIPLIERS.get(provider, _DEFAULT_CACHE_MULTIPLIERS)

    usd = (
        usage.input_tokens * input_rate
        + usage.cache_write_tokens * input_rate * cache_write_mult
        + usage.cached_read_tokens * input_rate * cache_read_mult
    ) / 1_000_000
    usd += usage.output_tokens * output_rate / 1_000_000

    rate, rate_date = get_usd_thb_rate()
    return Cost(
        usd=round(usd, 6),
        thb=round(usd * rate, 4),
        usd_thb_rate=rate,
        rate_source_date=rate_date,
        provider=provider,
        model=model,
        pricing_as_of=PRICING_AS_OF,
        is_estimate=True,
    )
