"""Env-based config. No API key ever lives in code -- read from the
environment only (see .env.example / repo hygiene rules)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None
    model: str
    max_upload_mb: int
    cors_origins: list[str]
    extraction_timeout_seconds: int


def load_config() -> Config:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        model=os.environ.get("TOR_MODEL", "claude-opus-5"),
        max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "50")),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        extraction_timeout_seconds=int(os.environ.get("EXTRACTION_TIMEOUT_SECONDS", "300")),
    )
