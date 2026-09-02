"""Env-based config. No API key ever lives in code -- read from the
environment only (see .env.example / repo hygiene rules).

Provider selection is operator-only by design: there is no per-request or
per-user provider choice, so no key ever crosses the API boundary.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Which env var holds the key for each provider. Falls back to a single
# generic var so an OpenAI-compatible endpoint doesn't need its own name.
_KEY_ENV_BY_PROVIDER = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai_compat": "TOR_PROVIDER_API_KEY",
}


@dataclass(frozen=True)
class Config:
    provider: str
    api_key: str | None
    provider_base_url: str | None
    model: str
    max_upload_mb: int
    cors_origins: list[str]
    extraction_timeout_seconds: int
    group_overrides: dict[str, tuple[str, str]]


def _load_group_overrides() -> dict[str, tuple[str, str]]:
    """TOR_GROUP_<GROUPNAME>="<provider>:<model>" -- e.g.
    TOR_GROUP_QUALIFICATIONS=anthropic:claude-opus-5 keeps the expensive model
    only for the group that needs it (see .env.example)."""
    overrides: dict[str, tuple[str, str]] = {}
    for key, value in os.environ.items():
        if not key.startswith("TOR_GROUP_") or ":" not in value:
            continue
        provider, _, model = value.partition(":")
        if provider and model:
            overrides[key[len("TOR_GROUP_") :].lower()] = (provider, model)
    return overrides


def api_key_for_provider(provider: str) -> str | None:
    """Look up an API key for an arbitrary provider name, independent of
    which provider is the document default. Needed because a per-group
    override (TOR_GROUP_<GROUP>) can, in principle, name a different
    provider than TOR_PROVIDER -- each provider's key lives in its own
    env var, so the override can't just reuse config.api_key."""
    key_env = _KEY_ENV_BY_PROVIDER.get(provider, "TOR_PROVIDER_API_KEY")
    return os.environ.get(key_env)


def load_config() -> Config:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    provider = os.environ.get("TOR_PROVIDER", "anthropic")
    return Config(
        provider=provider,
        api_key=api_key_for_provider(provider),
        provider_base_url=os.environ.get("TOR_PROVIDER_BASE_URL"),
        model=os.environ.get("TOR_MODEL", "claude-opus-5"),
        max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "50")),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        extraction_timeout_seconds=int(os.environ.get("EXTRACTION_TIMEOUT_SECONDS", "300")),
        group_overrides=_load_group_overrides(),
    )
