"""Provider port: the only thing llm/client.py is allowed to know about an
LLM vendor.

One operation only -- "constrain this model's output to this Pydantic
schema and tell me the token usage". Everything else (retry policy, the
FieldGroup split, merging group results, cost math) stays provider-neutral
in client.py and derive/, so adding a vendor never touches extraction logic.

Usage is deliberately NOT modelled on Anthropic's field names. Anthropic
reports cache writes and cache reads separately; OpenAI reports only a
cached-read count; several OpenAI-compatible stacks report neither. The
neutral shape keeps zeros for whatever a provider does not report, and
`ProviderCapabilities.reports_token_usage` says whether the numbers mean
anything at all (a self-hosted endpoint may return none, which makes cost
estimation impossible rather than free -- see derive/pricing.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ProviderError(RuntimeError):
    """Base for every provider failure, so callers never import a vendor SDK."""


class ProviderAuthError(ProviderError):
    """Credentials missing, malformed, or rejected."""


class ProviderRateLimitError(ProviderError):
    """Provider asked us to slow down."""


class ProviderAPIError(ProviderError):
    """Any other non-success response from the provider."""


class ProviderUnsupportedError(ProviderError):
    """Provider cannot satisfy a hard requirement (e.g. no native
    structured output). Raised at config/registry time, not mid-request."""


@dataclass(frozen=True)
class SystemBlock:
    """One system-prompt segment. `cacheable` is a hint, not a guarantee --
    providers without prompt caching ignore it and simply concatenate."""

    text: str
    cacheable: bool = False


@dataclass
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int = 0
    cached_read_tokens: int = 0


@dataclass(frozen=True)
class ProviderCapabilities:
    native_structured_output: bool
    prompt_caching: bool
    reports_token_usage: bool


@dataclass
class ProviderResult:
    parsed: BaseModel
    usage: ProviderUsage


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def complete_structured(
        self,
        *,
        system_blocks: list[SystemBlock],
        user_message: str,
        schema: type[BaseModel],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        """Return a schema-valid instance plus token usage.

        Must raise the neutral ProviderError subclasses above -- never a
        vendor SDK exception. Must let pydantic.ValidationError propagate
        unchanged, because client.py's retry loop keys on it.
        """
        ...
