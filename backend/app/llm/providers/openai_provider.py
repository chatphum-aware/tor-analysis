"""OpenAI adapter.

Confirmed by static introspection of the installed SDK (openai==2.48.0,
no live API call needed for this part -- see scripts/spike_provider.py for
the one thing that DOES need a live call):
  - `client.chat.completions.parse(model=, messages=, response_format=)`
    exists and accepts a Pydantic model directly for `response_format`.
    This wraps OpenAI's "Structured Outputs" (`strict: true` JSON schema
    enforcement), which is genuine API-level schema constraint, not just a
    prompted JSON mode -- justifies `native_structured_output=True`.
  - `openai.AuthenticationError`, `RateLimitError`, `APIStatusError` all
    exist as top-level exception types.
  - `CompletionUsage` fields: `prompt_tokens`, `completion_tokens`,
    `total_tokens`, `prompt_tokens_details` (which itself has
    `cached_tokens` and `cache_write_tokens`).

NOT yet confirmed by a live call (see scripts/spike_provider.py): whether
`completion.choices[0].message.parsed` reliably returns a real schema
instance on our actual group schemas (vs. a refusal/None), and whether
`cache_write_tokens` is ever actually non-zero in practice (OpenAI's cache
is usually described as read-only from the caller's perspective -- this
field may only populate for specific caching-eligible request shapes).

Two differences from Anthropic worth knowing:
  - No explicit prompt-caching API. OpenAI caches long prompt prefixes
    automatically and reports hits in usage; there is no `cache_control` to
    set, so SystemBlock.cacheable is ignored and `prompt_caching` is False.
  - System blocks are concatenated into one system message, because the
    chat API takes flat message content rather than a list of typed blocks.
"""
from __future__ import annotations

import openai
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


class OpenAIProvider:
    name = "openai"
    capabilities = ProviderCapabilities(
        native_structured_output=True,
        prompt_caching=False,
        reports_token_usage=True,
    )

    def __init__(self, api_key: str | None, base_url: str | None = None) -> None:
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

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
            completion = self._client.chat.completions.parse(
                model=model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_message},
                ],
                response_format=schema,
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            # Sibling of APIStatusError (both under APIError), not a subclass --
            # covers network blips and APITimeoutError (its own subclass).
            raise ProviderAPIError(f"openai API error: {exc}") from exc
        except openai.APIStatusError as exc:
            raise ProviderAPIError(f"openai API error: {exc}") from exc

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            # A refusal or a truncated response. Raise ProviderAPIError rather
            # than returning an empty document -- the project forbids silently
            # returning a crippled result.
            raise ProviderAPIError(
                f"openai returned no parsed output for model {model} "
                f"(finish_reason={completion.choices[0].finish_reason})"
            )

        raw = completion.usage
        details = raw.prompt_tokens_details if raw is not None else None
        return ProviderResult(
            parsed=parsed,
            usage=ProviderUsage(
                input_tokens=raw.prompt_tokens if raw is not None else 0,
                output_tokens=raw.completion_tokens if raw is not None else 0,
                cache_write_tokens=getattr(details, "cache_write_tokens", 0) or 0,
                cached_read_tokens=getattr(details, "cached_tokens", 0) or 0,
            ),
        )
