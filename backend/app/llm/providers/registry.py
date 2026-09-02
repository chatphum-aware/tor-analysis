"""Provider selection and the capability gate.

Operator decision (2026-09-02): native structured output is mandatory. A
provider that cannot constrain output to a schema at the API level is
refused HERE, at config load, rather than failing mid-extraction -- the
project's traceability rules (#2/#3) depend on API-level enforcement, and
discovering that a provider cannot honour them halfway through a paid
document is strictly worse than refusing to start.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.openai_compat_provider import OpenAICompatProvider
from app.llm.providers.openai_provider import OpenAIProvider
from app.llm.providers.base import LLMProvider, ProviderUnsupportedError

ProviderFactory = Callable[[Optional[str], Optional[str], Optional[str]], LLMProvider]

_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": lambda api_key, _base_url, _model: AnthropicProvider(api_key),
    "openai": lambda api_key, base_url, _model: OpenAIProvider(api_key, base_url),
    "gemini": lambda api_key, _base_url, _model: GeminiProvider(api_key),
    # _model matters here (unlike the other three): the capability probe
    # constructs a real request against it, so a placeholder name 404s.
    "openai_compat": lambda api_key, base_url, model: OpenAICompatProvider(
        api_key, base_url, probe_model=model
    ),
}

PROVIDER_NAMES: tuple[str, ...] = tuple(_FACTORIES)


def get_provider(
    name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ProviderUnsupportedError(
            f"unknown provider {name!r}; valid options: {', '.join(PROVIDER_NAMES)}"
        )
    provider = factory(api_key, base_url, model)
    if not provider.capabilities.native_structured_output:
        raise ProviderUnsupportedError(
            f"provider {name!r} cannot enforce a response schema natively, which this "
            f"project requires (every extracted value must carry a verifiable source). "
            f"Refusing to start rather than risk unverifiable output."
        )
    return provider
