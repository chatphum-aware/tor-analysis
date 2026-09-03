"""Anthropic adapter -- a faithful move of what llm/client.py did before
this abstraction existed.

Preserved deliberately, because both were measured rather than assumed
(see llm/groups.py): the first two system blocks carry
`cache_control: ephemeral` and stay byte-identical across calls, and the
per-group instruction is the last, uncached block.
"""
from __future__ import annotations

import anthropic
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


class AnthropicProvider:
    name = "anthropic"
    capabilities = ProviderCapabilities(
        native_structured_output=True,
        prompt_caching=True,
        reports_token_usage=True,
    )

    def __init__(self, api_key: str | None) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete_structured(
        self,
        *,
        system_blocks: list[SystemBlock],
        user_message: str,
        schema: type[BaseModel],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        system = [
            {
                "type": "text",
                "text": block.text,
                **({"cache_control": {"type": "ephemeral"}} if block.cacheable else {}),
            }
            for block in system_blocks
        ]
        try:
            with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
                output_format=schema,
            ) as stream:
                response = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            # Sibling of APIStatusError (both under APIError), not a subclass --
            # covers network blips and APITimeoutError (its own subclass), neither
            # of which the APIStatusError catch below would ever see.
            raise ProviderAPIError(f"anthropic API error: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderAPIError(f"anthropic API error: {exc.message}") from exc

        parsed = response.parsed_output
        if parsed is None:
            # A truncated/max-tokens-cut response. Raise rather than let a
            # None flow into client.py's parsed.model_dump() as an
            # AttributeError -- this needs to trigger rule #5's retry.
            raise ProviderAPIError(
                f"anthropic returned no parsed output for model {model} "
                f"(stop_reason={response.stop_reason})"
            )

        raw = response.usage
        return ProviderResult(
            parsed=parsed,
            usage=ProviderUsage(
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cache_write_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
                cached_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
            ),
        )
