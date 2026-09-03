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


@dataclass(frozen=True)
class ImageBlock:
    """One rendered page image, for a scanned PDF page with no text layer.

    Deliberately a separate type from SystemBlock rather than an image
    variant of it: every vendor SDK puts images in the USER turn, not the
    system prompt, so folding them into SystemBlock would describe a shape
    no adapter could actually send. `page` lets an adapter build a caption
    ("read page N from this image") without the caller having to pre-format
    one; `data` is raw bytes -- each adapter base64-encodes it however its
    own SDK wants."""

    page: int
    media_type: str  # "image/png" or "image/jpeg"
    data: bytes


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
    # Whether this provider/endpoint can be trusted with image input at all.
    # Deliberately NOT auto-probed the way native_structured_output is for
    # openai_compat: a wrong/ignored schema reliably fails validation, so a
    # probe can detect it -- but an endpoint that silently ignores an image
    # and answers from the caption text alone produces schema-valid,
    # plausible-looking output with no way to tell the difference. See
    # openai_compat_provider.py for how that gap is handled instead.
    vision_input: bool


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
        images: list[ImageBlock],
        user_message: str,
        schema: type[BaseModel],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        """Return a schema-valid instance plus token usage.

        `images` is `[]` on every call that isn't reading a scanned PDF page
        -- callers must check `capabilities.vision_input` before passing a
        non-empty list (client.py does this once, before running any group,
        not per-adapter).

        Must raise the neutral ProviderError subclasses above -- never a
        vendor SDK exception. Must let pydantic.ValidationError propagate
        unchanged, because client.py's retry loop keys on it.
        """
        ...
