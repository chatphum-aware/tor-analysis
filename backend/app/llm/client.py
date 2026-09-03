"""Calls Claude to extract a TOR document, one FieldGroup at a time (see
groups.py for why), with prompt caching and rule #5's "retry once, then
error clearly" behavior applied per group.

Caching note (see groups.py's module docstring for the measured details):
each group's differing `output_format` schema breaks the cache prefix, so
in practice every group pays the full cache-write cost -- caching here
only pays off on a same-group validation retry, or re-running the same
document+group again later within the TTL. Groups still run strictly
sequentially (never in parallel), which remains correct regardless: it's
what keeps a same-group retry or a later identical call able to hit
whatever cache entry exists, and avoids the alternative failure mode of
N parallel calls each independently writing a cache entry for a group
result that then never gets read.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ValidationError

from app.derive.pricing import Cost, Usage, compute_cost
from app.llm.groups import SHARED_RULES, FieldGroup
from app.llm.providers.base import LLMProvider, ProviderAPIError, SystemBlock
from app.models.schema import TORDocumentExtracted

MAX_TOKENS = 8_000  # per group call -- each group covers a small schema slice
# Confirmed live (2026-09-02) that this is NOT a safe universal default for
# reasoning models accessed via the openai_compat provider: openai/gpt-oss-120b
# on Groq produced a very long, coherent chain-of-thought for the 5-field
# `misc` group that consumed the entire 8000-token budget before ever
# emitting the final JSON -- a hard truncation (output_parse_failed), not a
# schema-enforcement failure (the same model passed the openai_compat
# capability probe cleanly with enough budget). Same underlying phenomenon
# as Gemini's thinking tokens (see gemini_provider.py), just more verbose
# for this particular model. Not raised here as a shared default because
# there's no evidence Anthropic or OpenAI's own models need it -- if a
# reasoning-heavy openai_compat model is used routinely, that model likely
# needs its own larger MAX_TOKENS, which argues for a per-provider (or
# per-group) token budget rather than raising the global default blindly.
MAX_RETRIES = 1  # rule #5: retry once on validation failure, then error clearly


class ExtractionValidationError(RuntimeError):
    """Raised when one group's output fails validation twice in a row."""


@dataclass
class ExtractionRunResult:
    document: TORDocumentExtracted
    usage: Usage
    duration_ms: int
    provider: str
    model: str
    cost: Cost | None


def _extract_one_group(
    provider: LLMProvider,
    *,
    document_text: str,
    model: str,
    group: FieldGroup,
) -> tuple[BaseModel, Usage, int]:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        instruction = group.instruction
        if attempt > 0:
            # A blind resend wastes the retry -- the model gets no signal about
            # what was wrong, so it's just a second independent roll of the dice
            # (confirmed root cause of two real validation failures in eval: the
            # model asserted a value with no source, and retrying identically
            # gave it no way to notice or fix that). Feed the exact validation
            # error back so the retry has a real chance to self-correct.
            instruction = (
                f"{group.instruction}\n\n"
                f"ความพยายามครั้งก่อนตอบผิดพลาด ต้องแก้ไขให้ตรงตาม schema ในครั้งนี้:\n{last_error}"
            )
        system_blocks = [
            SystemBlock(text=SHARED_RULES, cacheable=True),
            SystemBlock(text=document_text, cacheable=True),
            SystemBlock(text=instruction, cacheable=False),
        ]

        started = time.monotonic()
        try:
            result = provider.complete_structured(
                system_blocks=system_blocks,
                user_message=(
                    f"สกัดข้อมูลกลุ่ม '{group.name}' ตาม schema จากเอกสารข้างต้นให้ครบทุกฟิลด์"
                ),
                schema=group.schema,
                model=model,
                max_tokens=MAX_TOKENS,
            )
        except (ValidationError, ProviderAPIError) as exc:
            # A reasoning model can exhaust MAX_TOKENS on internal reasoning
            # before ever emitting JSON (ProviderAPIError from an empty/
            # truncated response) -- that's just as retryable as a schema
            # violation under rule #5, not a hard failure on attempt 1.
            last_error = exc
            continue

        duration_ms = int((time.monotonic() - started) * 1000)
        usage = Usage(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_write_tokens=result.usage.cache_write_tokens,
            cached_read_tokens=result.usage.cached_read_tokens,
        )
        return result.parsed, usage, duration_ms

    raise ExtractionValidationError(
        f"group '{group.name}' failed validation on {MAX_RETRIES + 1} attempts; "
        f"refusing to return partial/crippled data. last error: {last_error}"
    )


def extract(
    *,
    document_text: str,
    provider: LLMProvider,
    model: str,
    groups: list[FieldGroup],
    provider_for: Callable[[str, str], LLMProvider] | None = None,
) -> ExtractionRunResult:
    """`provider_for` resolves a group's override (name, model) to a provider
    instance. Required only if some group sets `provider`; a plain
    single-provider run can omit it (see Task 5's per-group override).
    Takes the model too, not just the provider name -- an openai_compat
    override needs the actual model to run its construction-time capability
    probe against (probing a placeholder model name 404s)."""
    merged: dict = {}
    total_usage = Usage(0, 0, 0, 0)
    total_duration_ms = 0
    usage_by_pair: dict[tuple[str, str], Usage] = {}

    for group in groups:
        group_model = group.model or model
        group_provider = provider
        if group.provider is not None:
            if provider_for is None:
                raise ExtractionValidationError(
                    f"group '{group.name}' overrides provider to '{group.provider}' but no "
                    f"provider_for resolver was supplied"
                )
            group_provider = provider_for(group.provider, group_model)

        parsed, usage, duration_ms = _extract_one_group(
            group_provider, document_text=document_text, model=group_model, group=group
        )
        merged.update(parsed.model_dump())
        total_usage.input_tokens += usage.input_tokens
        total_usage.output_tokens += usage.output_tokens
        total_usage.cache_write_tokens += usage.cache_write_tokens
        total_usage.cached_read_tokens += usage.cached_read_tokens
        total_duration_ms += duration_ms

        pair = (group_provider.name, group_model)
        pair_usage = usage_by_pair.setdefault(pair, Usage(0, 0, 0, 0))
        pair_usage.input_tokens += usage.input_tokens
        pair_usage.output_tokens += usage.output_tokens
        pair_usage.cache_write_tokens += usage.cache_write_tokens
        pair_usage.cached_read_tokens += usage.cached_read_tokens

    document = TORDocumentExtracted.model_validate(merged)

    # Report the (provider, model) pair(s) actually used -- never fall back to
    # the document-level default just because the used-pairs set happens to
    # collapse to one value, since that one value can be a non-default
    # override that doesn't match the default at all.
    pairs = sorted(usage_by_pair)
    if len(pairs) == 1:
        reported_provider, reported_model = pairs[0]
        cost = compute_cost(reported_provider, reported_model, total_usage)
    else:
        # A genuinely mixed run has no single (provider, model) a pricing
        # lookup can key on -- reporting it as the document default would
        # silently misattribute cost to a provider that may not have run at
        # all. Sum each pair's own real cost instead of guessing; if any
        # pair lacks pricing data, the honest total is unknown too (same
        # never-guess principle as compute_cost's own single-pair case).
        reported_provider = "mixed"
        reported_model = ",".join(f"{p}/{m}" for p, m in pairs)
        pair_costs = [compute_cost(p, m, usage_by_pair[(p, m)]) for p, m in pairs]
        if any(c is None for c in pair_costs):
            cost = None
        else:
            first = pair_costs[0]
            cost = Cost(
                usd=round(sum(c.usd for c in pair_costs), 6),
                thb=round(sum(c.thb for c in pair_costs), 4),
                usd_thb_rate=first.usd_thb_rate,
                rate_source_date=first.rate_source_date,
                provider=reported_provider,
                model=reported_model,
                pricing_as_of=first.pricing_as_of,
                is_estimate=True,
            )

    return ExtractionRunResult(
        document=document,
        usage=total_usage,
        duration_ms=total_duration_ms,
        provider=reported_provider,
        model=reported_model,
        cost=cost,
    )
