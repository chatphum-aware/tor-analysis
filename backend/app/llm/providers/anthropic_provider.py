"""Anthropic adapter -- a faithful move of what llm/client.py did before
this abstraction existed.

Preserved deliberately, because both were measured rather than assumed
(see llm/groups.py): the first two system blocks carry
`cache_control: ephemeral` and stay byte-identical across calls, and the
per-group instruction is the last, uncached block.
"""
from __future__ import annotations

import base64

import anthropic
from pydantic import BaseModel

from app.llm.providers.base import (
    ImageBlock,
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
        vision_input=True,
    )

    def __init__(self, api_key: str | None) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete_structured(
        self,
        *,
        system_blocks: list[SystemBlock],
        images: list[ImageBlock],
        user_message: str,
        schema: type[BaseModel],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        # Confirmed live, in two steps: Anthropic first rejected
        # `cache_control` on an empty text block, and after that was removed,
        # rejected the empty block outright ("text content blocks must be
        # non-empty"). This is new territory as of vision support --
        # `document_text` is legitimately "" for a fully scanned PDF (every
        # page is an image, nothing text-extracted at all), which never
        # reached this adapter before a scanned document was blanket-rejected
        # upstream. An empty block carries no information anyway, so it's
        # dropped rather than sent.
        system = [
            {
                "type": "text",
                "text": block.text,
                **({"cache_control": {"type": "ephemeral"}} if block.cacheable else {}),
            }
            for block in system_blocks
            if block.text
        ]
        # Images go in the user turn, never the system prompt -- that's true
        # of every vendor's API, not just Anthropic's. When there are none,
        # send the plain string exactly as before this feature existed, so
        # the proven text-only path has zero behavior change.
        if images:
            content: list[dict] = []
            for index, image in enumerate(images):
                content.append(
                    {"type": "text", "text": f"[หน้า {image.page} — ภาพหน้าเอกสารที่สแกน]"}
                )
                image_block: dict = {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    },
                }
                if index == len(images) - 1:
                    # Marks the whole caption+image run as a cached prefix,
                    # same principle as document_text's cache_control:
                    # user_message (the per-group instruction) comes after
                    # this and stays uncached, exactly like a group's
                    # instruction is the one uncached system block. This
                    # only pays off on a same-group retry, same limitation
                    # as document_text -- groups.py's own measured finding
                    # is that a differing output_format schema breaks the
                    # cache prefix ACROSS groups regardless of what's in it.
                    image_block["cache_control"] = {"type": "ephemeral"}
                content.append(image_block)
            content.append({"type": "text", "text": user_message})
        else:
            content = user_message
        try:
            with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
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
