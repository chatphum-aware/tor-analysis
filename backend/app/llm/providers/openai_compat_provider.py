"""Adapter for any OpenAI-API-compatible endpoint: Ollama, vLLM, llama.cpp
server, Together, Groq, Fireworks, OpenRouter, DeepInfra.

This is how Llama / Qwen / Mistral / DeepSeek are reached -- those are models,
not providers, and every practical way to serve them speaks this protocol.

Why the capability probe: the operator rule for this project is that a provider
must enforce the response schema natively. Whether a given endpoint can do that
depends on the SERVING STACK, not the model -- vLLM and recent Ollama support
schema-constrained decoding; several hosted aggregators accept only loose
"JSON mode"; some ignore the parameter entirely and return prose. A single
static capability flag would therefore be a lie for at least some endpoints, so
construction issues one tiny probe request and refuses the endpoint if it
cannot come back with schema-valid output.
"""
from __future__ import annotations

import copy

import openai
from pydantic import BaseModel, ValidationError

from app.llm.providers.base import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderRateLimitError,
    ProviderUnsupportedError,
    ProviderUsage,
    ProviderResult,
    SystemBlock,
)


def _make_strict_json_schema(schema: dict) -> dict:
    """OpenAI-compatible strict structured-output mode has two requirements
    a plain `schema.model_json_schema()` does not satisfy on its own --
    both confirmed live against Groq, one at a time, via real 400s:

      1. `additionalProperties: false` on EVERY object node (including
         nested models under `$defs`).
      2. EVERY key in `properties` must also appear in `required` --
         strict mode has no concept of an omittable field; our `Sourced[T]`
         fields that are semantically optional (`value`, `source`, `reason`
         all default to None) are already typed as nullable
         (`anyOf: [<type>, {"type": "null"}]`), so marking them required
         too is semantically correct: the model still returns `null` for
         them, it just can't omit the key.

    The `openai` SDK's own `.parse()` helper does both of these for you
    automatically (which is why OpenAIProvider never needed this); this
    adapter builds the request manually since not every OpenAI-compatible
    stack supports `.parse()`, so it has to do the same transform itself.
    Recurses through `$defs`/`properties`/`items`/`anyOf` etc. since Pydantic
    nests object schemas under all of these."""
    schema = copy.deepcopy(schema)

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                if "additionalProperties" not in node:
                    node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = list(node["properties"].keys())
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)
    return schema


class _ProbeSchema(BaseModel):
    """Deliberately trivial -- the probe tests whether the endpoint honours a
    schema at all, not whether it can handle our real 6-group schemas."""

    ok: bool


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        probe: bool = True,
        probe_model: str | None = None,
    ) -> None:
        if not base_url:
            raise ProviderUnsupportedError(
                "provider 'openai_compat' requires TOR_PROVIDER_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama, or your vLLM/Together/"
                "Groq/OpenRouter endpoint)"
            )
        # Many local stacks need no key but the SDK requires a non-empty string.
        self._client = openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url)
        self.capabilities = ProviderCapabilities(
            native_structured_output=True,  # provisional; the probe below confirms
            prompt_caching=False,
            reports_token_usage=True,
        )
        if probe:
            self._probe(probe_model)

    # Confirmed live against a reasoning model (openai/gpt-oss-120b via
    # Groq): a trivial {"ok": true} answer still consumed 74 output tokens,
    # because reasoning/thinking tokens come out of the same budget (the
    # same class of issue as Gemini's thinking tokens -- see
    # gemini_provider.py). A too-small probe budget produces a false
    # "this endpoint can't do structured output" rejection when the real
    # problem is just insufficient headroom, so the probe uses a generous
    # budget rather than the small one a trivial schema would suggest.
    _PROBE_MAX_TOKENS = 1000

    def _probe(self, probe_model: str | None) -> None:
        model = probe_model or "unknown"
        try:
            self.complete_structured(
                system_blocks=[SystemBlock(text="Reply with ok=true.")],
                user_message="ok?",
                schema=_ProbeSchema,
                model=model,
                max_tokens=self._PROBE_MAX_TOKENS,
            )
        except (ValidationError, ProviderAPIError) as exc:
            raise ProviderUnsupportedError(
                f"endpoint at this base_url could not return schema-valid output "
                f"for model {model!r}: {exc}. This project requires native schema "
                f"enforcement (every value must carry a verifiable source), so this "
                f"endpoint is refused rather than run with unverifiable output. If the "
                f"stack does support guided decoding, check the model name and that the "
                f"model is pulled/loaded."
            ) from exc

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
            completion = self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": _make_strict_json_schema(schema.model_json_schema()),
                        "strict": True,
                    },
                },
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
        except openai.APIStatusError as exc:
            raise ProviderAPIError(f"openai_compat API error: {exc}") from exc

        content = completion.choices[0].message.content
        if not content:
            raise ProviderAPIError(
                f"openai_compat endpoint returned empty content for model {model}"
            )
        # Let ValidationError propagate: client.py's retry loop keys on it, and a
        # stack that ignored the schema must fail loudly rather than half-parse.
        parsed = schema.model_validate_json(content)

        raw = completion.usage
        return ProviderResult(
            parsed=parsed,
            usage=ProviderUsage(
                input_tokens=getattr(raw, "prompt_tokens", 0) or 0,
                output_tokens=getattr(raw, "completion_tokens", 0) or 0,
            ),
        )
