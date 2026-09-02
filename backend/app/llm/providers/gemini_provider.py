"""Gemini adapter.

Confirmed by static introspection of the installed SDK (google-genai==1.47.0,
no live API call needed for this part -- see scripts/spike_provider.py for
what still needs one):
  - `client.models.generate_content(model=, contents=, config=)` exists;
    `config` accepts `response_mime_type`, `response_schema`,
    `system_instruction`, `max_output_tokens` as real fields of
    `types.GenerateContentConfig` (a plain dict works too -- the SDK coerces
    it).
  - `GenerateContentResponse` has a `.parsed` field directly.
  - `GenerateContentResponseUsageMetadata` fields: `prompt_token_count`,
    `candidates_token_count`, `cached_content_token_count`.
  - `google.genai.errors.ClientError(code, response_json, ...)` -- `.code`
    is a real instance attribute (confirmed: constructing one and reading
    `.code` back works). `ServerError` and `APIError` both exist too.

Confirmed by a live call (2026-09-02, gemini-3.6-flash): `.parsed` DOES
return a real schema instance directly (the `model_validate` fallback below
is defensive, not load-bearing for this model). Also confirmed, and this
is the important one: **thinking models report a separate
`thoughts_token_count` that is NOT included in `candidates_token_count`**
-- a real spike run showed 722 thinking tokens against only 299 output
tokens (65% of the whole request's tokens). Thinking tokens are billed as
output by Google's own pricing model, so leaving them out of
`output_tokens` would have silently undercounted cost by more than half on
any model with thinking enabled. Folded into `output_tokens` below.

NOT yet confirmed by a live call: the real numeric `.code` values Gemini
returns for auth vs. rate-limit failures (401/403/429 are the assumption
below, matching Google's general API conventions, not Gemini-specific
confirmation), and `cached_content_token_count` (the spike call didn't use
caching, so it's untested whether that field is ever populated in
practice).

Cost note, also from the live call: thinking models spend a LARGE and
variable share of the token budget on thinking (65-72% in two back-to-back
test calls on the same tiny document) -- this is real, billed output, not
free reasoning. `types.ThinkingConfig(thinking_budget=...)` exists to cap
or disable it, which would cut cost noticeably, but that's a quality/cost
tradeoff (thinking may be part of why the parsed output looked solid) for
a human to decide, not something this adapter should silently choose.
Also: a low `max_tokens` can fail outright (not just get truncated) if
thinking consumes the whole budget before any final JSON is written --
confirmed by reproducing it locally (max_tokens=2000 failed to parse,
max_tokens=8000, this project's actual MAX_TOKENS, succeeded on the
identical request).

Caching is deliberately not wired up here: Gemini's prompt caching is an
explicit server-side CachedContent resource with its own minimum-token
thresholds and TTL, not an inline marker on a block. This project's cache
prefix already fails to pay off across groups on Anthropic for the same
structural reason (a different schema per group -- see llm/groups.py), so
building Gemini's heavier caching flow would add real complexity for a
benefit already measured as near zero. `prompt_caching` is False and
SystemBlock.cacheable is ignored.
"""
from __future__ import annotations

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel

from app.llm.providers.base import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderRateLimitError,
    ProviderResult,
    ProviderUsage,
    SystemBlock,
)


class GeminiProvider:
    name = "gemini"
    capabilities = ProviderCapabilities(
        native_structured_output=True,
        prompt_caching=False,
        reports_token_usage=True,
    )

    def __init__(self, api_key: str | None) -> None:
        self._client = genai.Client(api_key=api_key)

    def complete_structured(
        self,
        *,
        system_blocks: list[SystemBlock],
        user_message: str,
        schema: type[BaseModel],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        system_text = "\n\n".join(block.text for block in system_blocks)
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=user_message,
                config={
                    "system_instruction": system_text,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "max_output_tokens": max_tokens,
                },
            )
        except genai_errors.ClientError as exc:
            # 401/403 -> auth, 429 -> rate limit, everything else -> API error
            code = getattr(exc, "code", None)
            if code in (401, 403):
                raise ProviderAuthError(str(exc)) from exc
            if code == 429:
                raise ProviderRateLimitError(str(exc)) from exc
            raise ProviderAPIError(f"gemini API error: {exc}") from exc
        except genai_errors.ServerError as exc:
            raise ProviderAPIError(f"gemini server error: {exc}") from exc

        parsed = response.parsed
        if parsed is None:
            raise ProviderAPIError(f"gemini returned no parsable output for model {model}")
        if not isinstance(parsed, schema):
            parsed = schema.model_validate(parsed)

        raw = response.usage_metadata
        # Thinking tokens (thoughts_token_count) are a SEPARATE field from
        # candidates_token_count and are billed as output -- confirmed live,
        # see the module docstring. Must be added in, not just candidates.
        output_tokens = 0
        if raw is not None:
            output_tokens = (raw.candidates_token_count or 0) + (raw.thoughts_token_count or 0)
        return ProviderResult(
            parsed=parsed,
            usage=ProviderUsage(
                input_tokens=(raw.prompt_token_count or 0) if raw is not None else 0,
                output_tokens=output_tokens,
                cache_write_tokens=0,
                cached_read_tokens=(raw.cached_content_token_count or 0) if raw is not None else 0,
            ),
        )
