"""Token usage -> cost in USD and THB. All arithmetic lives here in Python --
the model only ever returns raw token counts (rule #1: the LLM computes
nothing). See the plan's "Show tokens used and cost in Thai baht" section.

Pricing is keyed by model id because development happens on a cheaper model
(Haiku/Sonnet) while eval numbers that get published are run on Opus 5 --
a single hardcoded rate would misreport one or the other.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# USD per 1M tokens. Cached from the claude-api skill's Current Models
# table (Anthropic first-party API rates) -- verify against
# https://docs.claude.com/en/docs/about-claude/pricing before relying on
# this for anything beyond a rough estimate; prices change.
PRICING_AS_OF = "2026-06-24"

_PRICE_PER_MTOK_USD: dict[str, tuple[float, float]] = {
    # model_id: (input, output)
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Prompt caching multipliers, relative to the model's input rate.
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10

_DEFAULT_USD_THB_RATE = 36.50
_DEFAULT_USD_THB_RATE_DATE = "2026-08-28"


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class Cost:
    usd: float
    thb: float
    usd_thb_rate: float
    rate_source_date: str
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


def compute_cost(model: str, usage: Usage) -> Cost | None:
    """Returns None if the model isn't in the pricing table -- callers must
    surface that as "cost unknown", never guess a price (same principle as
    rule #3: no silent guessing to fill a slot).
    """
    prices = _PRICE_PER_MTOK_USD.get(model)
    if prices is None:
        return None
    input_rate, output_rate = prices

    usd = (
        usage.input_tokens * input_rate
        + usage.cache_creation_input_tokens * input_rate * _CACHE_WRITE_MULTIPLIER
        + usage.cache_read_input_tokens * input_rate * _CACHE_READ_MULTIPLIER
    ) / 1_000_000
    usd += usage.output_tokens * output_rate / 1_000_000

    rate, rate_date = get_usd_thb_rate()
    return Cost(
        usd=round(usd, 6),
        thb=round(usd * rate, 4),
        usd_thb_rate=rate,
        rate_source_date=rate_date,
        model=model,
        pricing_as_of=PRICING_AS_OF,
        is_estimate=True,
    )
