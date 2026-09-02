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

import anthropic
from pydantic import BaseModel, ValidationError

from app.derive.pricing import Usage
from app.llm.groups import SHARED_RULES, FieldGroup
from app.models.schema import TORDocumentExtracted

MAX_TOKENS = 8_000  # per group call -- each group covers a small schema slice
MAX_RETRIES = 1  # rule #5: retry once on validation failure, then error clearly


class ExtractionValidationError(RuntimeError):
    """Raised when one group's output fails validation twice in a row."""


@dataclass
class ExtractionRunResult:
    document: TORDocumentExtracted
    usage: Usage
    duration_ms: int
    model: str


def _extract_one_group(
    client: "anthropic.Anthropic",
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
        system = [
            {"type": "text", "text": SHARED_RULES, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": document_text, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": instruction},  # NOT cached -- varies per group and per retry
        ]

        started = time.monotonic()
        try:
            with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": f"สกัดข้อมูลกลุ่ม '{group.name}' ตาม schema จากเอกสารข้างต้นให้ครบทุกฟิลด์",
                    }
                ],
                output_format=group.schema,
            ) as stream:
                response = stream.get_final_message()
        except ValidationError as exc:
            last_error = exc
            continue

        duration_ms = int((time.monotonic() - started) * 1000)
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        )
        return response.parsed_output, usage, duration_ms

    raise ExtractionValidationError(
        f"group '{group.name}' failed validation on {MAX_RETRIES + 1} attempts; "
        f"refusing to return partial/crippled data. last error: {last_error}"
    )


def extract(
    *,
    document_text: str,
    api_key: str,
    model: str,
    groups: list[FieldGroup],
) -> ExtractionRunResult:
    client = anthropic.Anthropic(api_key=api_key)

    merged: dict = {}
    total_usage = Usage(0, 0, 0, 0)
    total_duration_ms = 0

    for group in groups:
        parsed, usage, duration_ms = _extract_one_group(
            client, document_text=document_text, model=model, group=group
        )
        merged.update(parsed.model_dump())
        total_usage.input_tokens += usage.input_tokens
        total_usage.output_tokens += usage.output_tokens
        total_usage.cache_creation_input_tokens += usage.cache_creation_input_tokens
        total_usage.cache_read_input_tokens += usage.cache_read_input_tokens
        total_duration_ms += duration_ms

    document = TORDocumentExtracted.model_validate(merged)
    return ExtractionRunResult(document=document, usage=total_usage, duration_ms=total_duration_ms, model=model)
