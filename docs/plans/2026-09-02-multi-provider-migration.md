# Multi-Provider LLM Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator run TOR extraction against Anthropic, OpenAI, Gemini, or any OpenAI-compatible endpoint (Ollama / vLLM / Together / Groq / OpenRouter) by changing environment variables only, without weakening the schema's source-traceability guarantees.

**Architecture:** Introduce a thin `LLMProvider` port in `backend/app/llm/providers/` that exposes exactly one operation — "given cacheable system blocks, a user message, and a Pydantic schema, return a validated instance plus token usage." `llm/client.py` keeps all retry/merge/group-sequencing logic and talks only to that port. Four adapters implement it: `anthropic`, `openai`, `gemini`, and one `openai_compat` adapter that covers every OpenAI-API-compatible stack via a configurable `base_url`. A capability contract lets the registry refuse, at startup, any provider that cannot enforce a schema natively.

**Tech Stack:** Python 3.12 (Docker) / 3.9 (local venv), FastAPI, Pydantic v2, `anthropic` SDK (existing), `openai` SDK (new), `google-genai` SDK (new), pytest, React + TypeScript (frontend contract only).

## Global Constraints

- **Python floor:** `requires-python = ">=3.12"` in `backend/pyproject.toml`. Local dev venv is 3.9 and relies on `eval_type_backport` for `X | None` syntax — do not remove `from __future__ import annotations` from any file.
- **Hard rule #1 — the model never computes.** All arithmetic (percentages, BE→CE dates) stays in Python. No adapter may add inference-side math.
- **Hard rule #2 — every non-null value carries a `source` (page + verbatim quote).** Enforced by the `Sourced` validator in `backend/app/models/schema.py:73-84`. No adapter may relax it.
- **Hard rule #3 — a null value carries a `reason`.** Same validator.
- **Native structured output is mandatory** (operator decision, 2026-09-02). A provider that cannot constrain output to a schema at the API level is rejected at config load, not at request time.
- **Provider choice is operator-only, via env vars.** No end-user provider/key selection, no API surface for it, no frontend picker.
- **No secrets in code or git.** Keys come from the environment only. `.env` is gitignored; only `.env.example` is committed.
- **Never commit directly** — route through `/quick-commit` (user's CLAUDE.md rule). The `git commit` steps below describe intent; the operator runs the skill.
- **Cost gate:** any step that calls a real provider API costs real money. Every such step is marked **💸 COSTS MONEY** and must be confirmed with the user before running.

---

## Impact / Risk Check

Required by CLAUDE.md. Every claim below came from a grep over the repo on 2026-09-02, not from assumption.

### 1. Usages & callers

- **`llm.client.extract()` — 3 callers**, all of which pass `api_key=config.anthropic_api_key` and a model string:
  - `app/api/extract.py:67-74` (HTTP endpoint, wrapped in `run_in_threadpool` + `asyncio.wait_for`)
  - `app/run_extraction.py:67-72` (CLI)
  - `app/eval/run_eval.py:319-324` (eval harness)
- **`derive.pricing.compute_cost()` — 2 production callers + 5 test call sites:**
  - `app/derive/calculations.py:108`
  - `app/eval/run_eval.py:357`
  - `tests/unit/test_pricing.py:6,19,28,35,44`
- **`anthropic.*` exception types caught in 2 files** — these are the only places provider SDK types leak out of `llm/`:
  - `app/api/extract.py:83,85,89` (`AuthenticationError`, `RateLimitError`, `APIStatusError`)
  - `app/run_extraction.py:76,79,82` (same three)
- **`anthropic` SDK imported in 3 files:** `app/llm/client.py:21`, `app/api/extract.py:12`, `app/run_extraction.py:17`.
- **`config.anthropic_api_key` read in 4 places:** `api/extract.py:29,71`, `run_extraction.py:37,69`, `eval/run_eval.py:291,321`, `config.py:11,21`.

### 2. Shared — what breaks in more than one place at once

- **`pricing.Usage` (`app/derive/pricing.py:42-46`) is shared by 6 modules:** `llm/client.py:24`, `derive/calculations.py:11`, `eval/run_eval.py:58`, `tests/unit/test_api.py:8`, `tests/unit/test_export_csv.py:3`, `tests/unit/test_calculations.py:7`. Renaming its fields touches all of them.
- **The Anthropic-specific cache field names have leaked into the public API response and the frontend.** `cache_creation_input_tokens` / `cache_read_input_tokens` appear in:
  - `app/models/schema.py:165-166` (`ExtractionUsage`, part of the `/api/extract` response)
  - `frontend/src/types/schema.ts:98-99`
  - `frontend/src/components/UsageFooter.tsx:10-11`
  - plus `pricing.py:45-46,83-84`, `client.py:94-95,125-126`, `calculations.py:154-155`, `run_extraction.py:113`, `eval/run_eval.py:349-350`, `tests/unit/test_pricing.py:16-17`, `tests/unit/test_calculations.py:126`
- **`models/schema.py` is the single source of truth for three consumers at once** (its own module docstring says so): the extraction call, the API response, and the eval scorer. Any change to it invalidates the hand-annotated `backend/tests/expected/*.json` ground truth.
- **`frontend/src/types/schema.ts` is a hand-maintained copy of `schema.py` — there is no codegen** (documented in `PROGRESS.md`). Every backend schema change needs a manual frontend edit or the two silently drift.
- **The 6-way `FieldGroup` split (`app/llm/groups.py`) exists solely because of an Anthropic limit** ("compiled grammar is too large", documented at length in that file's docstring). It is not a provider-neutral constant — each new provider has its own schema-complexity ceiling.

### 3. Regression risk

| Change | What could break | Mitigation |
|---|---|---|
| Rename usage cache fields | Frontend `UsageFooter` renders `undefined`; `tsc -b` will **not** catch it if the interface is edited to match but the backend isn't (or vice versa) | Task 4 changes both sides in one commit and adds a backend test asserting the serialized JSON key names |
| Move/alias `pricing.Usage` | 6 import sites, 3 of them tests | Keep `Usage = ProviderUsage` alias in `pricing.py` so existing imports keep working unchanged |
| Change `compute_cost()` signature | 2 prod + 5 test call sites | Task 3 updates all 7 in the same commit |
| Replace `anthropic.*` excepts with neutral ones | A provider error could become an unhandled 500 instead of a mapped 429/502 | Task 2 adds tests that each neutral exception maps to the right HTTP status |
| Reuse the 6-group split on a new provider | A provider with a lower schema ceiling fails mid-extraction with a confusing error; one with a higher ceiling wastes 6x the calls | Task 9 validates the split per provider before that provider is declared supported |
| Weaker/cheaper models on any provider | This session's eval proved cheap models violate rules #1–#3 in ways stronger ones don't (4 distinct fields across 3 documents) | Task 5's per-group override + Task 9's eval gate; no provider ships without an eval run |
| Adding SDK dependencies | Docker image size, transitive conflicts with `anthropic`/`fastapi` | Each provider SDK is added in its own task, with `pip install` + full `pytest` run before commit |

### 4. Blast radius

**Modified:** `backend/app/llm/client.py`, `backend/app/llm/groups.py`, `backend/app/config.py`, `backend/app/derive/pricing.py`, `backend/app/derive/calculations.py`, `backend/app/models/schema.py`, `backend/app/api/extract.py`, `backend/app/run_extraction.py`, `backend/app/eval/run_eval.py`, `backend/pyproject.toml`, `.env.example`, `frontend/src/types/schema.ts`, `frontend/src/components/UsageFooter.tsx`, `backend/tests/unit/test_pricing.py`, `backend/tests/unit/test_calculations.py`.

**Created:** `backend/app/llm/providers/{__init__,base,registry,anthropic_provider,openai_provider,gemini_provider,openai_compat_provider}.py`, `backend/tests/unit/test_providers.py`, `backend/tests/unit/test_provider_registry.py`, `backend/scripts/spike_provider.py`.

**Not touched:** all PDF/Thai text handling (`app/pdf/`, `app/thai/`), the extraction prompts (`app/llm/prompts/*.md`), `tests/expected/*.json` ground truth, every frontend component except `UsageFooter.tsx`.

### 5. Verify

Run after **every** task:
```bash
cd backend && .venv/bin/python -m pytest tests/unit -q      # must stay 42+ passed
cd frontend && npx tsc -b                                    # must stay clean
```
Run after Tasks 2, 4, and 9:
```bash
cd /Users/chatphum.a/Sites/tor-analysis && docker compose up -d --build
curl -s localhost:8000/api/health                            # {"status":"ok"}
```
Run once per provider, at the end of that provider's task (**💸 COSTS MONEY**):
```bash
cd backend && set -a && source ../.env && set +a
.venv/bin/python -m app.eval.run_eval --model <model>        # compare against baseline below
```

**Baseline to beat (established this session, `claude-opus-5`, 3 documents):** 185/215 fields exact, 0 missed, 0 extraction crashes. A provider scoring materially worse is a finding to report, not a reason to silently ship.

---

## Scope Note: a framing correction worth making before you start

The request named "llama, chat-gpt, gemini, openai, qwen" as providers. **Llama and Qwen are models, not providers** — they have no API of their own. You reach them through a serving stack (Ollama, vLLM, llama.cpp) or an aggregator (Together, Groq, Fireworks, OpenRouter, DeepInfra). Nearly all of those expose an **OpenAI-compatible** HTTP API.

That collapses the work considerably:

| Adapter | Covers |
|---|---|
| `anthropic` | Claude (existing behavior, preserved) |
| `openai` | GPT models on OpenAI's own API |
| `gemini` | Google Gemini |
| `openai_compat` | Llama, Qwen, Mistral, DeepSeek, … via Ollama / vLLM / Together / Groq / Fireworks / OpenRouter — anything with a `base_url` and an OpenAI-shaped `/chat/completions` |

**Consequence for your "native structured output required" rule:** whether a `openai_compat` endpoint can enforce a schema depends on the *serving stack*, not the model. Ollama and vLLM support schema-constrained decoding; some aggregators only support loose "JSON mode"; some support neither. A single adapter therefore cannot have a static capability answer — Task 8 handles this with a **runtime capability probe** at config load, which is what makes the "refuse unsupported providers" rule enforceable rather than aspirational.

---

## File Structure

```
backend/app/llm/
├── client.py                    MODIFIED: keeps retry/merge/sequencing, talks only to LLMProvider
├── groups.py                    MODIFIED: FieldGroup gains optional provider/model override
└── providers/
    ├── __init__.py              NEW: empty (package marker, matches app/pdf, app/thai convention)
    ├── base.py                  NEW: SystemBlock, ProviderUsage, ProviderCapabilities,
    │                                 ProviderResult, LLMProvider protocol, neutral exceptions
    ├── registry.py              NEW: name -> factory, capability gate, config validation
    ├── anthropic_provider.py    NEW: wraps today's behavior exactly (caching + output_format)
    ├── openai_provider.py       NEW
    ├── gemini_provider.py       NEW
    └── openai_compat_provider.py NEW: base_url-driven, runtime capability probe

backend/scripts/
└── spike_provider.py            NEW: throwaway-but-committed probe; proves an SDK's structured
                                      output works against a real group schema before you
                                      write the adapter

backend/tests/unit/
├── test_providers.py            NEW: FakeProvider contract tests, no network
└── test_provider_registry.py    NEW: capability gate + config resolution, no network
```

One responsibility per file; `base.py` holds only types (no I/O), each adapter holds only one provider's translation, `registry.py` holds only selection/validation.

---

### Task 1: Provider port and neutral types (no network, no SDKs)

**Files:**
- Create: `backend/app/llm/providers/__init__.py`
- Create: `backend/app/llm/providers/base.py`
- Test: `backend/tests/unit/test_providers.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel` only.
- Produces — every later task depends on these exact names:
  - `SystemBlock(text: str, cacheable: bool = False)`
  - `ProviderUsage(input_tokens: int, output_tokens: int, cache_write_tokens: int = 0, cached_read_tokens: int = 0)`
  - `ProviderCapabilities(native_structured_output: bool, prompt_caching: bool, reports_token_usage: bool)`
  - `ProviderResult(parsed: BaseModel, usage: ProviderUsage)`
  - `LLMProvider` protocol with `name: str`, `capabilities: ProviderCapabilities`, and
    `complete_structured(*, system_blocks: list[SystemBlock], user_message: str, schema: type[BaseModel], model: str, max_tokens: int) -> ProviderResult`
  - `ProviderAuthError`, `ProviderRateLimitError`, `ProviderAPIError`, `ProviderUnsupportedError` (all subclass `ProviderError(RuntimeError)`)

- [x] **Step 1: Write the failing test**

Create `backend/tests/unit/test_providers.py`:

```python
from pydantic import BaseModel

from app.llm.providers.base import (
    LLMProvider,
    ProviderCapabilities,
    ProviderResult,
    ProviderUsage,
    SystemBlock,
)


class _Tiny(BaseModel):
    value: str


class FakeProvider:
    """Minimal in-memory LLMProvider used by every provider-layer test.
    Records the last call so tests can assert what client.py sent."""

    name = "fake"
    capabilities = ProviderCapabilities(
        native_structured_output=True, prompt_caching=True, reports_token_usage=True
    )

    def __init__(self, parsed=None, usage=None):
        self._parsed = parsed if parsed is not None else _Tiny(value="ok")
        self._usage = usage or ProviderUsage(input_tokens=10, output_tokens=5)
        self.calls: list[dict] = []

    def complete_structured(self, *, system_blocks, user_message, schema, model, max_tokens):
        self.calls.append(
            {
                "system_blocks": system_blocks,
                "user_message": user_message,
                "schema": schema,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        return ProviderResult(parsed=self._parsed, usage=self._usage)


def test_fake_provider_satisfies_protocol():
    assert isinstance(FakeProvider(), LLMProvider)


def test_system_block_defaults_to_not_cacheable():
    assert SystemBlock(text="hello").cacheable is False


def test_provider_usage_defaults_cache_fields_to_zero():
    usage = ProviderUsage(input_tokens=3, output_tokens=4)
    assert usage.cache_write_tokens == 0
    assert usage.cached_read_tokens == 0


def test_complete_structured_returns_parsed_and_usage():
    provider = FakeProvider()
    result = provider.complete_structured(
        system_blocks=[SystemBlock(text="rules", cacheable=True)],
        user_message="go",
        schema=_Tiny,
        model="fake-1",
        max_tokens=100,
    )
    assert result.parsed.value == "ok"
    assert result.usage.input_tokens == 10
    assert provider.calls[0]["model"] == "fake-1"
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llm.providers'`

- [x] **Step 3: Write minimal implementation**

Create `backend/app/llm/providers/__init__.py` as an empty file (matches the empty `__init__.py` in `app/pdf/`, `app/thai/`, `app/api/`).

Create `backend/app/llm/providers/base.py`:

```python
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
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_providers.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Full suite still green**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: `46 passed` (42 existing + 4 new)

- [x] **Step 6: Commit**

```bash
git add backend/app/llm/providers/__init__.py backend/app/llm/providers/base.py backend/tests/unit/test_providers.py
# then run /quick-commit; suggested message:
# "Add provider port and neutral usage/capability types"
```

---

### Task 2: Anthropic adapter + registry + rewire client.py (behavior-preserving)

This is the risky task: it must change *how* the Anthropic call is made without changing *what* it does. The existing 42 tests plus a byte-level assertion on the system blocks are the safety net.

**Files:**
- Create: `backend/app/llm/providers/anthropic_provider.py`
- Create: `backend/app/llm/providers/registry.py`
- Create: `backend/tests/unit/test_provider_registry.py`
- Modify: `backend/app/llm/client.py` (whole `_extract_one_group` / `extract` body)
- Modify: `backend/app/config.py` (add provider + neutral key resolution)
- Modify: `backend/app/api/extract.py:12,29,71,83-90` (drop `import anthropic`, map neutral errors)
- Modify: `backend/app/run_extraction.py:17,37,69,76-83` (same)
- Modify: `backend/app/eval/run_eval.py:291,321` (use neutral config fields)
- Modify: `.env.example`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces:
  - `AnthropicProvider(api_key: str | None)` implementing `LLMProvider`, `name = "anthropic"`
  - `registry.get_provider(name: str, *, api_key: str | None = None, base_url: str | None = None) -> LLMProvider`
  - `registry.PROVIDER_NAMES: tuple[str, ...]`
  - `Config.provider: str`, `Config.api_key: str | None`, `Config.provider_base_url: str | None` (`Config.anthropic_api_key` is **removed** — all 6 read sites migrate)
  - `client.extract(*, document_text, provider: LLMProvider, model, groups) -> ExtractionRunResult` (the `api_key: str` parameter is **replaced** by `provider`)

- [x] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_provider_registry.py`:

```python
import pytest

from app.llm.providers.base import ProviderUnsupportedError
from app.llm.providers.registry import PROVIDER_NAMES, get_provider


def test_anthropic_is_registered():
    assert "anthropic" in PROVIDER_NAMES


def test_unknown_provider_is_rejected_with_the_valid_list():
    with pytest.raises(ProviderUnsupportedError) as exc:
        get_provider("not-a-provider", api_key="x")
    assert "not-a-provider" in str(exc.value)
    for name in PROVIDER_NAMES:
        assert name in str(exc.value)


def test_anthropic_provider_declares_required_capabilities():
    provider = get_provider("anthropic", api_key="test-key-not-used")
    assert provider.name == "anthropic"
    assert provider.capabilities.native_structured_output is True
    assert provider.capabilities.prompt_caching is True
```

Append to `backend/tests/unit/test_providers.py` (reuses `FakeProvider` from Task 1):

```python
from app.llm.client import extract
from app.llm.groups import FieldGroup
from app.models.schema import BasicInfoGroup


def test_client_sends_shared_rules_and_document_as_cacheable_blocks():
    """The two big blocks must stay cacheable and in this order -- prompt
    caching is a strict byte-prefix match, so reordering silently destroys
    every cache hit (see llm/groups.py's measured findings)."""
    provider = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="do the thing")

    extract(document_text="DOC TEXT", provider=provider, model="m", groups=[group])

    blocks = provider.calls[0]["system_blocks"]
    assert [b.cacheable for b in blocks] == [True, True, False]
    assert blocks[1].text == "DOC TEXT"
    assert blocks[2].text == "do the thing"


def test_client_passes_group_schema_through_untouched():
    provider = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="i")

    extract(document_text="d", provider=provider, model="m", groups=[group])

    assert provider.calls[0]["schema"] is BasicInfoGroup
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_provider_registry.py tests/unit/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llm.providers.registry'`, and `TypeError: extract() got an unexpected keyword argument 'provider'`

- [x] **Step 3: Write the Anthropic adapter**

Create `backend/app/llm/providers/anthropic_provider.py`:

```python
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
        except anthropic.APIStatusError as exc:
            raise ProviderAPIError(f"anthropic API error: {exc.message}") from exc

        raw = response.usage
        return ProviderResult(
            parsed=response.parsed_output,
            usage=ProviderUsage(
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cache_write_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
                cached_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
            ),
        )
```

- [x] **Step 4: Write the registry**

Create `backend/app/llm/providers/registry.py`:

```python
"""Provider selection and the capability gate.

Operator decision (2026-09-02): native structured output is mandatory. A
provider that cannot constrain output to a schema at the API level is
refused HERE, at config load, rather than failing mid-extraction -- the
project's traceability rules (#2/#3) depend on API-level enforcement, and
discovering that a provider cannot honour them halfway through a paid
document is strictly worse than refusing to start.
"""
from __future__ import annotations

from typing import Callable

from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.base import LLMProvider, ProviderUnsupportedError

ProviderFactory = Callable[[str | None, str | None], LLMProvider]

_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": lambda api_key, _base_url: AnthropicProvider(api_key),
}

PROVIDER_NAMES: tuple[str, ...] = tuple(_FACTORIES)


def get_provider(
    name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ProviderUnsupportedError(
            f"unknown provider {name!r}; valid options: {', '.join(PROVIDER_NAMES)}"
        )
    provider = factory(api_key, base_url)
    if not provider.capabilities.native_structured_output:
        raise ProviderUnsupportedError(
            f"provider {name!r} cannot enforce a response schema natively, which this "
            f"project requires (every extracted value must carry a verifiable source). "
            f"Refusing to start rather than risk unverifiable output."
        )
    return provider
```

- [x] **Step 5: Rewire `client.py`**

Replace the whole body of `backend/app/llm/client.py` below the docstring with:

```python
from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.derive.pricing import Usage
from app.llm.groups import SHARED_RULES, FieldGroup
from app.llm.providers.base import LLMProvider, SystemBlock
from app.models.schema import TORDocumentExtracted

MAX_TOKENS = 8_000  # per group call -- each group covers a small schema slice
MAX_RETRIES = 1  # rule #5: retry once on validation failure, then error clearly


class ExtractionValidationError(RuntimeError):
    """Raised when one group's output fails validation twice in a row."""


@dataclass
class ExtractionRunResult:
    document: TORDocumentExtracted
    usage: Usage
    duration_ms: int
    model: str


def _extract_one_group(
    provider: LLMProvider,
    *,
    document_text: str,
    model: str,
    group: FieldGroup,
) -> tuple[BaseModel, Usage, int]:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        instruction = group.instruction
        if attempt > 0:
            # A blind resend wastes the retry -- the model gets no signal about
            # what was wrong, so it's just a second independent roll of the dice
            # (confirmed root cause of two real validation failures in eval).
            instruction = (
                f"{group.instruction}\n\n"
                f"ความพยายามครั้งก่อนตอบผิดพลาด ต้องแก้ไขให้ตรงตาม schema ในครั้งนี้:\n{last_error}"
            )
        system_blocks = [
            SystemBlock(text=SHARED_RULES, cacheable=True),
            SystemBlock(text=document_text, cacheable=True),
            SystemBlock(text=instruction, cacheable=False),
        ]

        started = time.monotonic()
        try:
            result = provider.complete_structured(
                system_blocks=system_blocks,
                user_message=(
                    f"สกัดข้อมูลกลุ่ม '{group.name}' ตาม schema จากเอกสารข้างต้นให้ครบทุกฟิลด์"
                ),
                schema=group.schema,
                model=model,
                max_tokens=MAX_TOKENS,
            )
        except ValidationError as exc:
            last_error = exc
            continue

        duration_ms = int((time.monotonic() - started) * 1000)
        usage = Usage(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_write_tokens=result.usage.cache_write_tokens,
            cached_read_tokens=result.usage.cached_read_tokens,
        )
        return result.parsed, usage, duration_ms

    raise ExtractionValidationError(
        f"group '{group.name}' failed validation on {MAX_RETRIES + 1} attempts; "
        f"refusing to return partial/crippled data. last error: {last_error}"
    )


def extract(
    *,
    document_text: str,
    provider: LLMProvider,
    model: str,
    groups: list[FieldGroup],
) -> ExtractionRunResult:
    merged: dict = {}
    total_usage = Usage(0, 0, 0, 0)
    total_duration_ms = 0

    for group in groups:
        parsed, usage, duration_ms = _extract_one_group(
            provider, document_text=document_text, model=model, group=group
        )
        merged.update(parsed.model_dump())
        total_usage.input_tokens += usage.input_tokens
        total_usage.output_tokens += usage.output_tokens
        total_usage.cache_write_tokens += usage.cache_write_tokens
        total_usage.cached_read_tokens += usage.cached_read_tokens
        total_duration_ms += duration_ms

    document = TORDocumentExtracted.model_validate(merged)
    return ExtractionRunResult(
        document=document, usage=total_usage, duration_ms=total_duration_ms, model=model
    )
```

Note: the `Usage` field names above (`cache_write_tokens`, `cached_read_tokens`) are the Task 3 names. Task 3 renames them in `pricing.py`; until then this file will fail. Do Task 3's Step 3 first if you want a green tree at every commit — or land Tasks 2+3 as one commit.

- [x] **Step 6: Rewire `config.py`**

Replace `backend/app/config.py` with:

```python
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


def load_config() -> Config:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    provider = os.environ.get("TOR_PROVIDER", "anthropic")
    key_env = _KEY_ENV_BY_PROVIDER.get(provider, "TOR_PROVIDER_API_KEY")
    return Config(
        provider=provider,
        api_key=os.environ.get(key_env),
        provider_base_url=os.environ.get("TOR_PROVIDER_BASE_URL"),
        model=os.environ.get("TOR_MODEL", "claude-opus-5"),
        max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "50")),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        extraction_timeout_seconds=int(os.environ.get("EXTRACTION_TIMEOUT_SECONDS", "300")),
    )
```

- [x] **Step 7: Decouple the three callers from the `anthropic` SDK**

In `backend/app/api/extract.py`: delete `import anthropic` (line 12); add
`from app.llm.providers.base import ProviderAPIError, ProviderAuthError, ProviderRateLimitError`
and `from app.llm.providers.registry import get_provider`. Replace the `config.anthropic_api_key`
guard at line 29 with:

```python
    if not config.api_key:
        raise HTTPException(
            status_code=500,
            detail=f"ยังไม่ได้ตั้งค่า API key ของ provider '{config.provider}' บนเซิร์ฟเวอร์",
        )
```

Replace the `llm_extract` call arguments (lines 68-73) with:

```python
                llm_extract,
                document_text=document_text,
                provider=get_provider(
                    config.provider,
                    api_key=config.api_key,
                    base_url=config.provider_base_url,
                ),
                model=config.model,
                groups=FIELD_GROUPS,
```

Replace the three `anthropic.*` except blocks (lines 83-90) with:

```python
    except ProviderAuthError:
        raise HTTPException(
            status_code=500, detail=f"API key ของ provider '{config.provider}' ไม่ถูกต้อง"
        ) from None
    except ProviderRateLimitError:
        raise HTTPException(
            status_code=429, detail="ถูกจำกัดอัตราการเรียก API ลองใหม่อีกสักครู่"
        ) from None
    except ProviderAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
```

Apply the equivalent three edits to `backend/app/run_extraction.py` (lines 17, 37, 69, 76-83) and the two config-field reads in `backend/app/eval/run_eval.py` (lines 291, 321), constructing the provider the same way via `get_provider(...)`.

- [x] **Step 8: Update `.env.example`**

Add above the existing `TOR_MODEL` block:

```bash
# Which LLM provider to use: anthropic | openai | gemini | openai_compat
TOR_PROVIDER=anthropic

# API key for the selected provider. The variable name depends on TOR_PROVIDER:
#   anthropic     -> ANTHROPIC_API_KEY
#   openai        -> OPENAI_API_KEY
#   gemini        -> GEMINI_API_KEY
#   openai_compat -> TOR_PROVIDER_API_KEY
# Only openai_compat needs a base URL (Ollama, vLLM, Together, Groq, OpenRouter, ...)
# TOR_PROVIDER_BASE_URL=http://localhost:11434/v1
```

- [x] **Step 9: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: `51 passed` (46 + 3 registry + 2 client-wiring). If `test_api.py` fails, it is constructing `Config` positionally — update it to the new field order.

- [x] **Step 10: Verify the container still boots and serves**

```bash
cd /Users/chatphum.a/Sites/tor-analysis && docker compose up -d --build
curl -s localhost:8000/api/health   # expect {"status":"ok"}
```

- [x] **Step 11: 💸 COSTS MONEY — confirm behavior is genuinely unchanged**

Ask the user before running. One document, cheapest model:

```bash
cd backend && set -a && source ../.env && set +a
.venv/bin/python -m app.run_extraction outputs/samples/tor_2400.pdf --model claude-haiku-4-5
```
Expected: completes with no error; `cache_write` > 0 on the first group. Compare `project_name`, `agency`, `median_price` against `backend/tests/expected/tor_2400.json` — they must match.

- [x] **Step 12: Commit**

```bash
# /quick-commit; suggested message:
# "Route extraction through provider port, add Anthropic adapter"
```

---

### Task 3: Provider-namespaced pricing

**Files:**
- Modify: `backend/app/derive/pricing.py`
- Modify: `backend/app/derive/calculations.py:11,108,116,147-155`
- Modify: `backend/app/eval/run_eval.py:58,357`
- Modify: `backend/tests/unit/test_pricing.py` (all 5 `compute_cost` call sites)
- Modify: `backend/tests/unit/test_calculations.py:126`

**Interfaces:**
- Consumes: `ProviderUsage` from Task 1.
- Produces: `compute_cost(provider: str, model: str, usage: Usage) -> Cost | None`; `Usage` is now an alias of `ProviderUsage`; `Cost` gains `provider: str`.

- [x] **Step 1: Write the failing tests**

Replace the body of `backend/tests/unit/test_pricing.py` with (keeping its existing import style):

```python
from app.derive.pricing import Usage, compute_cost


def test_haiku_cost_is_computed_from_the_anthropic_table():
    cost = compute_cost("anthropic", "claude-haiku-4-5", Usage(1_000_000, 1_000_000))
    assert cost is not None
    assert cost.provider == "anthropic"
    assert cost.usd == 6.0  # 1.00 input + 5.00 output per Mtok


def test_cache_write_and_read_use_the_documented_multipliers():
    usage = Usage(
        input_tokens=0,
        output_tokens=0,
        cache_write_tokens=1_000_000,
        cached_read_tokens=1_000_000,
    )
    cost = compute_cost("anthropic", "claude-haiku-4-5", usage)
    assert cost is not None
    assert cost.usd == 1.35  # 1.00*1.25 write + 1.00*0.10 read


def test_unknown_model_returns_none_rather_than_guessing():
    assert compute_cost("anthropic", "some-future-model", Usage(1, 1)) is None


def test_same_model_name_on_a_different_provider_is_not_silently_reused():
    """A bare model name is not globally unique -- 'llama-3.1-70b' costs
    different amounts on Together vs Groq vs a local GPU."""
    assert compute_cost("openai_compat", "claude-haiku-4-5", Usage(1, 1)) is None


def test_thb_conversion_reports_the_rate_it_used():
    cost = compute_cost("anthropic", "claude-haiku-4-5", Usage(1, 1))
    assert cost is not None
    assert cost.thb == round(cost.usd * cost.usd_thb_rate, 4)
    assert cost.rate_source_date
```

- [x] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_pricing.py -v`
Expected: FAIL — `TypeError: compute_cost() takes 2 positional arguments but 3 were given`

- [x] **Step 3: Implement**

In `backend/app/derive/pricing.py`: delete the local `Usage` dataclass (lines 42-46) and add
`from app.llm.providers.base import ProviderUsage` plus `Usage = ProviderUsage` (keeps the 6
existing `from app.derive.pricing import Usage` imports working). Then:

```python
# USD per 1M tokens, keyed (provider, model) -- a bare model id is NOT unique
# across providers (the same open-weights model costs different amounts on
# every host). Verify against each provider's own pricing page before trusting
# these for anything but a rough estimate; prices change.
PRICING_AS_OF = "2026-06-24"

_PRICE_PER_MTOK_USD: dict[tuple[str, str], tuple[float, float]] = {
    # (provider, model_id): (input, output)
    ("anthropic", "claude-fable-5"): (10.00, 50.00),
    ("anthropic", "claude-mythos-5"): (10.00, 50.00),
    ("anthropic", "claude-opus-5"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-8"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-7"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-6"): (5.00, 25.00),
    ("anthropic", "claude-sonnet-5"): (2.00, 10.00),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-5"): (1.00, 5.00),
}
```

Add `provider: str` to the `Cost` dataclass, and change the function:

```python
def compute_cost(provider: str, model: str, usage: Usage) -> Cost | None:
    """Returns None if (provider, model) isn't in the pricing table -- callers
    must surface that as "cost unknown", never guess a price (same principle as
    rule #3: no silent guessing to fill a slot). Self-hosted endpoints will
    always land here, which is correct: GPU time is a real cost this table
    cannot know.
    """
    prices = _PRICE_PER_MTOK_USD.get((provider, model))
    if prices is None:
        return None
    input_rate, output_rate = prices

    usd = (
        usage.input_tokens * input_rate
        + usage.cache_write_tokens * input_rate * _CACHE_WRITE_MULTIPLIER
        + usage.cached_read_tokens * input_rate * _CACHE_READ_MULTIPLIER
    ) / 1_000_000
    usd += usage.output_tokens * output_rate / 1_000_000

    rate, rate_date = get_usd_thb_rate()
    return Cost(
        usd=round(usd, 6),
        thb=round(usd * rate, 4),
        usd_thb_rate=rate,
        rate_source_date=rate_date,
        provider=provider,
        model=model,
        pricing_as_of=PRICING_AS_OF,
        is_estimate=True,
    )
```

Then update the 2 production call sites: `derive/calculations.py:108` becomes
`compute_cost(provider, model, usage)` (add a `provider: str` keyword-only parameter to
`assemble_document`, and pass `provider=` from all 3 of its callers), and
`eval/run_eval.py:357` becomes `compute_cost(provider_name, model, total_usage)`.
Update the fallback `Cost(...)` literal in `calculations.py:111-119` to include `provider=provider`.

- [x] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: `51 passed`

- [x] **Step 5: Commit**

```bash
# /quick-commit; suggested message:
# "Key pricing table by (provider, model) pair"
```

---

### Task 4: Provider-neutral usage in the API response and frontend

**Breaking API change.** Doing it now, before other providers land, means only one contract break instead of one per provider.

**Files:**
- Modify: `backend/app/models/schema.py:162-166` (`ExtractionUsage`), `:177-190` (`ExtractionMeta`)
- Modify: `backend/app/derive/calculations.py:151-156`
- Modify: `backend/app/run_extraction.py:113`
- Modify: `backend/app/eval/run_eval.py:349-350`
- Modify: `frontend/src/types/schema.ts:96-100`
- Modify: `frontend/src/components/UsageFooter.tsx:8-16`
- Test: `backend/tests/unit/test_api.py` (add a serialized-key assertion)

**Interfaces:**
- Produces: `ExtractionUsage` with fields `input_tokens`, `output_tokens`, `cache_write_tokens`, `cached_read_tokens`; `ExtractionMeta` gains `provider: str`.

- [x] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_api.py`:

```python
def test_extraction_usage_json_keys_are_provider_neutral():
    """These key names are the public API contract and are mirrored by hand in
    frontend/src/types/schema.ts (there is no codegen). Anthropic's own field
    names must not leak into a provider-neutral response."""
    from app.models.schema import ExtractionUsage

    keys = set(ExtractionUsage(
        input_tokens=1, output_tokens=2, cache_write_tokens=3, cached_read_tokens=4
    ).model_dump().keys())
    assert keys == {"input_tokens", "output_tokens", "cache_write_tokens", "cached_read_tokens"}
```

- [x] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_api.py -k neutral -v`
Expected: FAIL — `ValidationError: cache_creation_input_tokens Field required`

- [x] **Step 3: Implement backend**

`backend/app/models/schema.py`:

```python
class ExtractionUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int  # 0 on providers without prompt caching
    cached_read_tokens: int  # 0 on providers that don't report cache hits
```

Add `provider: str` to `ExtractionMeta`, directly above its existing `model: str` field.
Update `calculations.py:151-156` to the new field names and pass `provider=provider` into
`ExtractionMeta`. Update `run_extraction.py:113` to print `cache_write={u.cache_write_tokens}
cache_read={u.cached_read_tokens}` and `eval/run_eval.py:349-350` to accumulate the new names.

- [x] **Step 4: Implement frontend**

`frontend/src/types/schema.ts` — replace the two cache lines in `ExtractionUsage`:

```typescript
export interface ExtractionUsage {
  input_tokens: number;
  output_tokens: number;
  cache_write_tokens: number;
  cached_read_tokens: number;
}
```

Add `provider: string;` to the `ExtractionMeta` interface above its `model` field.

`frontend/src/components/UsageFooter.tsx` — update the two field reads and surface the provider:

```tsx
        {usage.cache_write_tokens.toLocaleString("th-TH")} · cache read{" "}
        {usage.cached_read_tokens.toLocaleString("th-TH")}
```

and change the model line to `· {meta.provider}/{meta.model} ·`.

- [x] **Step 5: Verify both sides**

```bash
cd backend && .venv/bin/python -m pytest tests/unit -q     # expect 52 passed
cd ../frontend && npx tsc -b                                # expect clean
```

- [x] **Step 6: Regenerate eval ground truth expectations**

`tests/expected/*.json` intentionally exclude `extraction_meta`, so they are unaffected —
confirm with:

```bash
cd backend && grep -l extraction_meta tests/expected/*.json
```
Expected: no output. If any file matches, remove that key from it (the eval scorer drops it anyway).

- [x] **Step 7: Commit**

```bash
# /quick-commit; suggested message:
# "Make usage fields provider-neutral in API and frontend"
```

---

### Task 5: Per-group provider/model override

This is the piece deferred earlier this session specifically to be designed together with the multi-provider work. The eval found cheap models violating rules #1–#3 in `qualifications`, `key_dates`, `misc`, and `deliverables` — this lets those four groups run on a stronger model while the rest stay cheap.

**Files:**
- Modify: `backend/app/llm/groups.py` (`FieldGroup` dataclass)
- Modify: `backend/app/llm/client.py` (`extract` resolves per-group provider/model)
- Modify: `backend/app/config.py` (parse group overrides)
- Test: `backend/tests/unit/test_providers.py`

**Interfaces:**
- Produces: `FieldGroup(name, schema, instruction, provider: str | None = None, model: str | None = None)`; `Config.group_overrides: dict[str, tuple[str, str]]`; `extract(..., provider_for=...)` resolver callback.

- [x] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_providers.py`:

```python
def test_group_override_selects_a_different_provider_and_model():
    """Eval evidence (2026-09-02): cheap models violate the source/null rules
    in qualifications/key_dates/misc/deliverables but are fine elsewhere, so
    the model must be selectable per group, not per document."""
    cheap = FakeProvider(parsed=BasicInfoGroup.model_construct())
    strong = FakeProvider(parsed=BasicInfoGroup.model_construct())
    providers = {"cheap": cheap, "strong": strong}

    groups = [
        FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a"),
        FieldGroup(
            name="qualifications",
            schema=BasicInfoGroup,
            instruction="b",
            provider="strong",
            model="big-model",
        ),
    ]

    extract(
        document_text="d",
        provider=cheap,
        model="small-model",
        groups=groups,
        provider_for=lambda name: providers[name],
    )

    assert len(cheap.calls) == 1
    assert cheap.calls[0]["model"] == "small-model"
    assert len(strong.calls) == 1
    assert strong.calls[0]["model"] == "big-model"


def test_group_without_override_uses_the_default_provider():
    default = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a")

    extract(document_text="d", provider=default, model="m", groups=[group])

    assert len(default.calls) == 1
```

- [x] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_providers.py -k override -v`
Expected: FAIL — `TypeError: FieldGroup.__init__() got an unexpected keyword argument 'provider'`

- [x] **Step 3: Implement**

`backend/app/llm/groups.py`:

```python
@dataclass(frozen=True)
class FieldGroup:
    name: str
    schema: Type[BaseModel]
    instruction: str  # appended as the final, non-cached system block
    # Optional per-group override. Set when a group needs a different
    # provider/model than the document default -- eval showed cheap models
    # break the source/null rules on the list-heavy groups while handling the
    # flat ones fine. None means "use the document default".
    provider: str | None = None
    model: str | None = None
```

`backend/app/llm/client.py` — change `extract`'s signature and per-group resolution:

```python
def extract(
    *,
    document_text: str,
    provider: LLMProvider,
    model: str,
    groups: list[FieldGroup],
    provider_for: Callable[[str], LLMProvider] | None = None,
) -> ExtractionRunResult:
    """`provider_for` resolves a group's override name to a provider instance.
    Required only if some group sets `provider`; a plain single-provider run
    can omit it."""
    merged: dict = {}
    total_usage = Usage(0, 0, 0, 0)
    total_duration_ms = 0
    models_used: set[str] = set()

    for group in groups:
        group_provider = provider
        if group.provider is not None:
            if provider_for is None:
                raise ExtractionValidationError(
                    f"group '{group.name}' overrides provider to '{group.provider}' but no "
                    f"provider_for resolver was supplied"
                )
            group_provider = provider_for(group.provider)
        group_model = group.model or model
        models_used.add(f"{group_provider.name}/{group_model}")

        parsed, usage, duration_ms = _extract_one_group(
            group_provider, document_text=document_text, model=group_model, group=group
        )
        ...  # accumulation unchanged from Task 2
```

Set `ExtractionRunResult.model` to `model` when `len(models_used) == 1`, else to
`",".join(sorted(models_used))` so a mixed run is honestly labelled rather than
misreporting one model. Add `from typing import Callable` to the imports.

`backend/app/config.py` — parse overrides from env:

```python
def _load_group_overrides() -> dict[str, tuple[str, str]]:
    """TOR_GROUP_<GROUPNAME>="<provider>:<model>" -- e.g.
    TOR_GROUP_QUALIFICATIONS=anthropic:claude-opus-5 keeps the expensive model
    only for the group that needs it."""
    overrides: dict[str, tuple[str, str]] = {}
    for key, value in os.environ.items():
        if not key.startswith("TOR_GROUP_") or ":" not in value:
            continue
        provider, _, model = value.partition(":")
        if provider and model:
            overrides[key[len("TOR_GROUP_") :].lower()] = (provider, model)
    return overrides
```

Add `group_overrides: dict[str, tuple[str, str]]` to `Config` and populate it in `load_config()`.
In `api/extract.py`, apply overrides to `FIELD_GROUPS` before the call and pass
`provider_for=lambda name: get_provider(name, api_key=..., base_url=...)`.

- [x] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: `54 passed`

- [x] **Step 5: Document the override in `.env.example`**

```bash
# Optional: run specific field groups on a different provider/model.
# Format: TOR_GROUP_<GROUP>="<provider>:<model>"
# Groups: basic_info | key_dates | bonds | qualifications | deliverables | misc
# Eval (2026-09-02) found cheap models break the source/null rules on the
# list-heavy groups, so this is the cost/reliability lever:
# TOR_GROUP_QUALIFICATIONS=anthropic:claude-opus-5
# TOR_GROUP_KEY_DATES=anthropic:claude-opus-5
```

- [x] **Step 6: Commit**

```bash
# /quick-commit; suggested message:
# "Support per-group provider and model overrides"
```

---

### Task 6: OpenAI adapter

**Do not write this adapter from memory.** The parameter that constrains output to a schema
has changed name and shape across `openai` SDK versions. Step 1 discovers the real signature;
Steps 3+ match what it proved.

**Files:**
- Create: `backend/scripts/spike_provider.py`
- Create: `backend/app/llm/providers/openai_provider.py`
- Modify: `backend/app/llm/providers/registry.py` (register `openai`)
- Modify: `backend/pyproject.toml` (add `openai>=1.0`)
- Test: `backend/tests/unit/test_provider_registry.py`

**Interfaces:**
- Produces: `OpenAIProvider(api_key: str | None, base_url: str | None = None)` implementing `LLMProvider`, `name = "openai"`.

- [~] **Step 1: 💸 COSTS MONEY — write and run the discovery spike** (script written; SDK shape confirmed via static introspection of the installed openai==2.48.0 instead of spending money -- see the adapter's own docstring for exactly what's confirmed vs. still needs a live call)

Ask the user before running. Create `backend/scripts/spike_provider.py`:

```python
"""Provider capability spike. Proves a vendor SDK can (a) constrain output to
one of our real group schemas and (b) report token usage, BEFORE an adapter is
written against a remembered API shape.

Usage:
    OPENAI_API_KEY=... python scripts/spike_provider.py openai gpt-<model>
"""
from __future__ import annotations

import json
import os
import sys

from app.models.schema import BasicInfoGroup

DOC = """[หน้า 1]
ประกาศกรมสรรพากร
เรื่อง ประกวดราคาจ้างพนักงานรักษาความสะอาด ประจำปีงบประมาณ พ.ศ. 2569
ราคากลางของงานจ้าง เป็นเงินทั้งสิ้น 7,672,800.00 บาท
"""


def spike_openai(model: str) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    print("--- dir(client.chat.completions) ---")
    print([n for n in dir(client.chat.completions) if not n.startswith("_")])
    print("--- dir(client.beta.chat.completions) ---")
    print([n for n in dir(getattr(client.beta, "chat", object()).completions)
           if not n.startswith("_")] if hasattr(client.beta, "chat") else "no beta.chat")

    completion = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "Extract per the schema. Cite page and quote."},
            {"role": "user", "content": DOC},
        ],
        response_format=BasicInfoGroup,
    )
    print("--- parsed ---")
    print(completion.choices[0].message.parsed)
    print("--- usage repr (note the exact field names) ---")
    print(repr(completion.usage))
    print(json.dumps(completion.usage.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    provider, model = sys.argv[1], sys.argv[2]
    {"openai": spike_openai}[provider](model)
```

Run:
```bash
cd backend && .venv/bin/pip install "openai>=1.0"
set -a && source ../.env && set +a
.venv/bin/python scripts/spike_provider.py openai <model-id>
```

**Record from the output, before continuing:** the method that accepted the schema, the
attribute holding the parsed object, and the **exact** usage field names (in particular
whatever reports cached input tokens — it is nested under a details object, not a flat
field, and the name differs from Anthropic's). If `.parse()` does not exist on this SDK
version, the printed `dir()` listings show what does.

- [x] **Step 2: Write the failing registry test**

Append to `backend/tests/unit/test_provider_registry.py`:

```python
def test_openai_is_registered_and_declares_structured_output():
    provider = get_provider("openai", api_key="test-key-not-used")
    assert provider.name == "openai"
    assert provider.capabilities.native_structured_output is True
    assert provider.capabilities.prompt_caching is False  # no explicit cache_control API
```

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_provider_registry.py -k openai -v`
Expected: FAIL — `ProviderUnsupportedError: unknown provider 'openai'`

- [x] **Step 3: Write the adapter, matching the spike output**

Create `backend/app/llm/providers/openai_provider.py`. The skeleton below is correct in
structure; substitute the call shape and usage field names **from Step 1's output** where
marked:

```python
"""OpenAI adapter.

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
            completion = self._client.chat.completions.parse(  # <- confirm from spike
                model=model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_message},
                ],
                response_format=schema,  # <- confirm from spike
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
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
        return ProviderResult(
            parsed=parsed,
            usage=ProviderUsage(
                input_tokens=raw.prompt_tokens,
                output_tokens=raw.completion_tokens,
                cache_write_tokens=0,  # no separate write concept
                cached_read_tokens=getattr(
                    getattr(raw, "prompt_tokens_details", None), "cached_tokens", 0
                ) or 0,  # <- confirm exact path from spike
            ),
        )
```

Register it in `registry.py`:

```python
from app.llm.providers.openai_provider import OpenAIProvider

_FACTORIES: dict[str, ProviderFactory] = {
    "anthropic": lambda api_key, _base_url: AnthropicProvider(api_key),
    "openai": lambda api_key, base_url: OpenAIProvider(api_key, base_url),
}
```

Add `"openai>=1.0"` to `dependencies` in `backend/pyproject.toml`.

- [ ] **Step 4: Add pricing entries**

In `pricing.py`, add `("openai", "<model-id>"): (<input>, <output>)` for each model you
intend to run, taking the numbers from OpenAI's current pricing page (do not guess) and
bumping `PRICING_AS_OF` to today. Add a test asserting one of them resolves.

- [x] **Step 5: Verify**

```bash
cd backend && .venv/bin/python -m pytest tests/unit -q     # expect 56 passed
```

- [ ] **Step 6: 💸 COSTS MONEY — eval gate**

Ask the user first. Then:

```bash
cd backend && set -a && source ../.env && set +a
TOR_PROVIDER=openai .venv/bin/python -m app.eval.run_eval --model <model-id>
```

Compare against the baseline (185/215 exact, 0 missed, 0 crashes). Record the result in
`PROGRESS.md`. A provider that crashes on any of the 3 documents is **not** done — the
failure is a finding to investigate with the same method used this session (read the exact
validation error, check it against the document text, then fix the prompt or the adapter).

- [ ] **Step 7: Commit**

```bash
# /quick-commit; suggested message:
# "Add OpenAI provider adapter"
```

---

### Task 7: Gemini adapter

Same spike-first discipline. Gemini's schema parameter, its caching model (explicit cached
content objects rather than inline markers), and its usage field names all differ from both
providers above.

**Files:**
- Modify: `backend/scripts/spike_provider.py` (add `spike_gemini`)
- Create: `backend/app/llm/providers/gemini_provider.py`
- Modify: `backend/app/llm/providers/registry.py`, `backend/pyproject.toml`, `backend/app/derive/pricing.py`
- Test: `backend/tests/unit/test_provider_registry.py`

**Interfaces:**
- Produces: `GeminiProvider(api_key: str | None)` implementing `LLMProvider`, `name = "gemini"`.

- [x] **Step 1: 💸 COSTS MONEY — extend the spike** (run live against gemini-3.6-flash -- note: gemini-2.5-flash from the plan is deprecated, the API's own 404 pointed to the replacement. Found and fixed a real bug: `thoughts_token_count` (thinking tokens, 65-72% of total tokens in testing) was NOT being counted in output_tokens -- would have silently undercounted cost by more than half. Also confirmed max_tokens=2000 fails to parse outright if thinking consumes the whole budget; this project's actual MAX_TOKENS=8000 was sufficient. See gemini_provider.py's docstring.)

Add to `backend/scripts/spike_provider.py`:

```python
def spike_gemini(model: str) -> None:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    print("--- dir(client.models) ---")
    print([n for n in dir(client.models) if not n.startswith("_")])

    response = client.models.generate_content(
        model=model,
        contents=DOC,
        config={
            "response_mime_type": "application/json",
            "response_schema": BasicInfoGroup,
            "system_instruction": "Extract per the schema. Cite page and quote.",
        },
    )
    print("--- .parsed ---")
    print(response.parsed)
    print("--- usage_metadata repr (note exact field names) ---")
    print(repr(response.usage_metadata))
```

and register it in the dispatch dict: `{"openai": spike_openai, "gemini": spike_gemini}`.

Run:
```bash
cd backend && .venv/bin/pip install "google-genai>=1.0"
set -a && source ../.env && set +a
.venv/bin/python scripts/spike_provider.py gemini <model-id>
```

**Record:** whether `response.parsed` returns a real `BasicInfoGroup` (if it returns a dict,
the adapter must call `schema.model_validate(...)` itself), and the exact
`usage_metadata` field names for prompt / candidates / cached token counts.

- [x] **Step 2: Write the failing test**

```python
def test_gemini_is_registered_and_declares_structured_output():
    provider = get_provider("gemini", api_key="test-key-not-used")
    assert provider.name == "gemini"
    assert provider.capabilities.native_structured_output is True
```

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_provider_registry.py -k gemini -v`
Expected: FAIL — `ProviderUnsupportedError: unknown provider 'gemini'`

- [x] **Step 3: Write the adapter, matching the spike output**

Create `backend/app/llm/providers/gemini_provider.py`:

```python
"""Gemini adapter.

Differences that matter here:
  - Schema goes in a `config` dict (`response_schema` + JSON mime type),
    not as a top-level parameter.
  - Caching is an explicit server-side CachedContent resource with its own
    minimum-token thresholds and TTL, not an inline marker on a block. Not
    wired up: this project's cache prefix already fails to pay off across
    groups on Anthropic for the same structural reason (a different schema
    per group), so building Gemini's heavier caching flow would add real
    complexity for a benefit measurement already showed is near zero.
    `prompt_caching` is therefore False and SystemBlock.cacheable is ignored.
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
        if not isinstance(parsed, schema):  # <- confirm need from spike
            parsed = schema.model_validate(parsed)

        raw = response.usage_metadata
        return ProviderResult(
            parsed=parsed,
            usage=ProviderUsage(
                input_tokens=raw.prompt_token_count or 0,       # <- confirm from spike
                output_tokens=raw.candidates_token_count or 0,  # <- confirm from spike
                cache_write_tokens=0,
                cached_read_tokens=getattr(raw, "cached_content_token_count", 0) or 0,
            ),
        )
```

Register `"gemini": lambda api_key, _base_url: GeminiProvider(api_key)`, add
`"google-genai>=1.0"` to `pyproject.toml`, and add `("gemini", "<model>")` pricing rows
from Google's current pricing page.

- [x] **Step 4: Verify**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: `57 passed`

- [~] **Step 5: 💸 COSTS MONEY — eval gate** (2/3 documents completed and scored: 112/127 fields exact (88%), 0 missed on the covered fields, 0 crashes -- notably `deliverables[].days_from_signing` is 12/12 exact, where Haiku earlier this session hallucinated computed day-counts on the same field. 3rd document (`tor_2733`) hit Google's FREE TIER daily quota mid-run -- confirmed real: 20 requests/day for gemini-3.6-flash, `generate_content_free_tier_requests` quota, not a code bug or paid-tier rate limit. No money was spent on any Gemini testing today. Also found and fixed a SECOND missed field-rename site (run_eval.py's usage accumulation) -- same bug class as run_extraction.py's, from the same Task 4 rewrite. Re-run tor_2733 once the daily quota resets, or on a paid tier, to complete this step.)

Ask first, then `TOR_PROVIDER=gemini .venv/bin/python -m app.eval.run_eval --model <model-id>`.
Record in `PROGRESS.md` against the baseline.

- [ ] **Step 6: Commit**

```bash
# /quick-commit; suggested message:
# "Add Gemini provider adapter"
```

---

### Task 8: OpenAI-compatible adapter with runtime capability probe (Llama / Qwen / self-hosted)

This is what actually delivers "Llama and Qwen". It reuses the OpenAI SDK against a custom
`base_url`, and — because schema enforcement depends on the serving stack, not the model —
**probes** the endpoint at construction time so the "refuse providers without native
structured output" rule is enforced by evidence rather than by an assumption baked into a
constant.

**Files:**
- Create: `backend/app/llm/providers/openai_compat_provider.py`
- Modify: `backend/app/llm/providers/registry.py`
- Test: `backend/tests/unit/test_provider_registry.py`

**Interfaces:**
- Produces: `OpenAICompatProvider(api_key: str | None, base_url: str | None, probe: bool = True)`, `name = "openai_compat"`.

- [x] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_provider_registry.py`:

```python
import pytest

from app.llm.providers.base import ProviderUnsupportedError
from app.llm.providers.openai_compat_provider import OpenAICompatProvider


def test_openai_compat_requires_a_base_url():
    """Without base_url this would silently talk to api.openai.com with a
    local-endpoint key, which is both confusing and a key-leak risk."""
    with pytest.raises(ProviderUnsupportedError) as exc:
        OpenAICompatProvider(api_key="x", base_url=None, probe=False)
    assert "TOR_PROVIDER_BASE_URL" in str(exc.value)


def test_openai_compat_reports_no_usage_confidence_by_default():
    """Self-hosted stacks frequently return zeroed or absent usage, which must
    surface as 'cost unknown' rather than 'cost zero'."""
    provider = OpenAICompatProvider(
        api_key="x", base_url="http://localhost:11434/v1", probe=False
    )
    assert provider.name == "openai_compat"
    assert provider.capabilities.prompt_caching is False
```

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_provider_registry.py -k compat -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.llm.providers.openai_compat_provider'`

- [x] **Step 2: Implement**

Create `backend/app/llm/providers/openai_compat_provider.py`:

```python
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

import openai
from pydantic import BaseModel, ValidationError

from app.llm.providers.base import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderRateLimitError,
    ProviderResult,
    ProviderUnsupportedError,
    ProviderUsage,
    SystemBlock,
)


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

    def _probe(self, probe_model: str | None) -> None:
        model = probe_model or "unknown"
        try:
            self.complete_structured(
                system_blocks=[SystemBlock(text="Reply with ok=true.")],
                user_message="ok?",
                schema=_ProbeSchema,
                model=model,
                max_tokens=64,
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
                        "schema": schema.model_json_schema(),
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
```

Register it:

```python
"openai_compat": lambda api_key, base_url: OpenAICompatProvider(api_key, base_url),
```

- [x] **Step 3: Verify unit tests**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: `59 passed`

- [x] **Step 4: Verify against a real endpoint** (used Groq -- a hosted
  OpenAI-compatible endpoint, not local Ollama -- with `openai/gpt-oss-120b`,
  a reasoning model. Found and fixed THREE real bugs, each confirmed by an
  actual 400 response, not guessed:
  1. `get_provider()` never threaded the actual model into `openai_compat`'s
     factory, so the capability probe always ran against the literal string
     `"unknown"` -> 404. Fixed by adding `model` to `get_provider()` and to
     `provider_for`'s signature (now `(name, model)` not just `(name)`) --
     this also required updating client.py's per-group override resolution
     and all 3 call sites (api/extract.py, run_extraction.py, run_eval.py).
  2. OpenAI-compatible strict mode rejected a plain `schema.model_json_schema()`:
     needs `additionalProperties: false` on every object node, AND every
     property key listed in `required` (optionality is expressed via nullable
     types, not omission -- our `Sourced[T]` fields already are nullable, so
     this is semantically correct, not a schema weakening). The `openai` SDK's
     own `.parse()` does this for real OpenAI automatically; this manually-built
     request doesn't get that for free. Fixed with `_make_strict_json_schema()`,
     verified programmatically against the full 26-leaf TORDocumentExtracted
     schema (every object node consistent) before spending anything on a retry.
  3. The probe's `max_tokens=64` was too small for a reasoning model -- a
     trivial `{"ok": true}` answer still consumed 74 tokens because reasoning
     tokens share the budget (same phenomenon as Gemini's thinking tokens).
     Raised to 1000, confirmed live.
  After all three fixes, the probe passes cleanly. The `misc` group (5 fields)
  then hit `MAX_TOKENS=8000` truncation mid-reasoning -- confirmed via the
  API's own `failed_generation` field showing a long, coherent, unfinished
  chain-of-thought, not a schema failure. This is a genuine characteristic of
  this specific model, not an adapter bug (documented in client.py rather than
  silently raising the shared MAX_TOKENS default for every provider). Stopped
  here per the user's choice rather than spending more to chase a full
  successful extraction with this particular verbose model.)

If Ollama is available locally this costs nothing but GPU/CPU time:

```bash
ollama pull qwen2.5:7b
cd backend && TOR_PROVIDER=openai_compat TOR_PROVIDER_BASE_URL=http://localhost:11434/v1 \
  TOR_MODEL=qwen2.5:7b .venv/bin/python -m app.run_extraction outputs/samples/tor_2400.pdf
```

Two outcomes, both informative:
- **Refused at startup** with the `ProviderUnsupportedError` message → the stack doesn't
  enforce schemas; that is the rule working as designed, not a bug. Record which stack/version.
- **Runs** → note that `cost` will be `None` (no pricing row for self-hosted, by design) and
  compare field output against `tests/expected/tor_2400.json`. Expect materially worse
  accuracy than Opus; that is the finding, and it belongs in `PROGRESS.md`.

- [ ] **Step 5: Commit**

```bash
# /quick-commit; suggested message:
# "Add OpenAI-compatible adapter for self-hosted and aggregator endpoints"
```

---

### Task 9: Per-provider group-split validation and cross-provider eval report

The 6-way split is an Anthropic artifact. This task stops it from being an unexamined
constant and produces the comparison table that makes the provider choice an evidence-based
decision rather than a preference.

**Files:**
- Create: `backend/app/eval/compare_providers.py`
- Modify: `PROGRESS.md`, `README.md`

**Interfaces:**
- Consumes: `registry.get_provider`, `eval.run_eval.score_document`, `FIELD_GROUPS`.
- Produces: `compare_providers.main()` writing a markdown comparison table.

- [ ] **Step 1: Add a schema-ceiling check**

Create `backend/app/eval/compare_providers.py` with a `--check-schema-ceiling` mode that,
for the selected provider, attempts one call per group with a deliberately trivial document
and reports which groups the provider accepts. This surfaces a too-large-grammar rejection
as a clear per-group report instead of a mid-document failure:

```python
"""Cross-provider comparison for the TOR extraction eval.

Two modes:
  --check-schema-ceiling  one cheap call per FieldGroup, reporting which
                          group schemas this provider will even accept. The
                          6-way split exists because of an Anthropic limit
                          ("compiled grammar is too large"); every provider
                          has its own ceiling, and discovering it per group
                          up front is far cheaper than hitting it mid-run.
  --eval                  full eval per provider, emitting one markdown table
                          so accuracy and cost are compared side by side.
"""
```

Implement `--check-schema-ceiling` to loop `FIELD_GROUPS`, call
`provider.complete_structured(...)` with a two-line stub document and `max_tokens=512`,
and print `OK` / the exact error per group.

- [ ] **Step 2: 💸 COSTS MONEY — run the ceiling check per provider**

Ask first. Then, per configured provider:

```bash
cd backend && set -a && source ../.env && set +a
.venv/bin/python -m app.eval.compare_providers --check-schema-ceiling --provider openai --model <id>
```
Expected: `OK` for all 6 groups. Any rejection means that provider needs its own split —
record the failing group and its error verbatim.

- [ ] **Step 3: 💸 COSTS MONEY — run the full comparison**

```bash
.venv/bin/python -m app.eval.compare_providers --eval \
  --provider anthropic --model claude-opus-5 \
  --provider openai --model <id> \
  --provider gemini --model <id>
```

- [ ] **Step 4: Record results honestly**

Append the generated table to `PROGRESS.md` and add a one-paragraph summary to `README.md`'s
Evaluation section. Report counts, not percentages (n=3). Include crashes and `missed`
counts, not just `exact` — a provider that silently returns fewer fields is not "almost as
good". Explicitly note which providers were refused by the capability gate and why.

- [ ] **Step 5: Commit**

```bash
# /quick-commit; suggested message:
# "Add cross-provider eval comparison and schema-ceiling check"
```

---

## Open Questions

Flag these to the user rather than deciding them silently mid-implementation:

1. **Breaking the API usage field names (Task 4)** — renaming `cache_creation_input_tokens` → `cache_write_tokens` is the honest fix for a provider-neutral contract, but it is a breaking change to `/api/extract`'s response for the sake of naming. The cheap alternative is keeping Anthropic's names everywhere and documenting the leak. Task 4 assumes the rename; say so now if you'd rather not.
2. **Gemini prompt caching is deliberately not implemented** (Task 7). Justification: this session already measured that the cache prefix cannot pay off across groups because each group sends a different schema, and Gemini's caching is a heavier explicit-resource flow. If a single-group or repeated-document workload appears later, revisit.
3. **Self-hosted cost reporting is intentionally `None`**, not `0` (Task 8). GPU time is a real cost the pricing table cannot know, and reporting `฿0.00` would be actively misleading in the UI. The frontend already handles a null-ish cost; confirm the display reads acceptably.
4. **The eval set is 3 documents.** Every per-provider number this plan produces carries that caveat. If provider choice is going to drive real spend, growing the fixture set is the higher-value work — and `fetch_samples.py` already supports it.

## Self-Review

- **Spec coverage:** all providers named in the request are reachable — Claude (Task 2), GPT/OpenAI (Task 6), Gemini (Task 7), Llama + Qwen via the OpenAI-compatible adapter (Task 8). Operator-only env-var selection: Tasks 2 and 5. "Refuse without native structured output": enforced in `registry.get_provider` (Task 2) and probed at runtime for the one adapter where it genuinely varies (Task 8). The deferred per-group override: Task 5.
- **Placeholder scan:** no TBDs. The three points where I would otherwise be guessing at an external SDK's current signature are handled by real discovery spikes with runnable commands (Tasks 6 Step 1, 7 Step 1), with the uncertain lines marked `<- confirm from spike` rather than asserted as fact.
- **Type consistency:** `ProviderUsage`/`SystemBlock`/`ProviderResult`/`ProviderCapabilities`/`LLMProvider` are defined once in Task 1 and used with identical names and field names throughout; `pricing.Usage` is an alias of `ProviderUsage`, so the 6 existing import sites keep working; `compute_cost(provider, model, usage)` has the same 3-argument shape in Tasks 3, 6, 7, and 9.
- **Known gap:** Task 2 temporarily depends on Task 3's renamed `Usage` fields. Called out in Task 2 Step 5 — land Tasks 2 and 3 together, or apply Task 3 Step 3 first, if you want every intermediate commit green.
