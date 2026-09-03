# TOR Analyzer — project guide

Extracts structured data from Thai government TOR / procurement documents using an LLM.
The product promise is **traceability, not just answers**: every extracted value must be
checkable against the source PDF. Most rules below exist to protect that promise.

## The five hard rules

These are cited by number throughout the code (`schema.py`, `pricing.py`, `calculations.py`,
`client.py`) and stated to the model in `backend/app/llm/prompts/extract_system.md`. This is
the authoritative definition. **Do not relax any of them to make a model or a provider pass.**

1. **The LLM never computes anything.** No percentages, no Buddhist-Era→Common-Era date
   conversion, no summing, no estimating. It returns only raw values found on a page.
   All arithmetic happens in Python (`app/derive/`). *Logical inference counts as computing*:
   "the document says price-only, so technical weight must be 0%" is a rule #1 violation,
   because no document ever wrote that 0.
2. **Every non-null value carries a `source`** — a locator anchoring it to an exact place
   in the source document, plus a verbatim quote. The locator's shape depends on the
   document's format, because "page" is a PDF concept: `text_page` (PDF text layer) and
   `vision_page` (a scanned PDF page read from a rendered image) carry a page number;
   `paragraph`/`table_cell_docx` carry a paragraph index or table coordinates; `cell_xlsx`
   carries sheet + cell. A `Source.kind` field says which, and the validator in
   `schema.py` enforces that a kind carries exactly its own locator fields and no others.
   For `vision_page`, `quote` is the model's best-effort transcription of the image rather
   than byte-for-byte extracted text — which is exactly why that kind stays distinct from
   `text_page` rather than being folded into it.
3. **A null value carries a `reason`**, never a guess to fill the slot.
4. **Every field carries a `confidence`** (`high`/`medium`/`low`), including null ones.
5. **Retry once on validation failure, then fail loudly.** Never return a partial or
   crippled document. The retry must feed the validation error back to the model — a blind
   resend wastes the attempt (this was a real, diagnosed bug).

Rules #2–#4 are enforced mechanically by the `Sourced` validator in
`backend/app/models/schema.py`. Rule #1 is enforced structurally: the model-facing
`TORDocumentExtracted` deliberately omits every derived field. Rule #5 lives in
`backend/app/llm/client.py`.

## Traps that have already bitten us

- **`app/models/schema.py` is the source of truth for three consumers at once**: the
  extraction call, the API response, and the eval scorer. Changing it also invalidates the
  hand-annotated ground truth in `backend/tests/expected/*.json`.
- **`frontend/src/types/schema.ts` is a hand-maintained copy of `schema.py`. There is no
  codegen.** Change one, change the other, or they drift silently.
- **Never `cat`/read the root `.env`** — it holds a real API key. To check a variable use
  `grep '^VAR=' .env`; to run something with it, `set -a; source ../.env; set +a`.
- **The 6-way `FieldGroup` split (`app/llm/groups.py`) is not a free knob.** It exists
  because one combined schema is rejected with "compiled grammar is too large". Each
  provider has its own ceiling — validate per provider before changing the split.
- **Cross-group prompt caching does not work, and this was measured.** Each group sends a
  different schema, which breaks the byte-prefix match, so every group pays a full cache
  write. Caching only helps a same-group retry. Don't "optimize" it without re-measuring.
- **`usable_text_ratio == 100%` does not mean the text is readable.** One real sample
  scored 100% while producing scrambled ASCII, because its font was mislabeled and had no
  `/ToUnicode` CMap. Neither `usable_text_ratio` nor `find_glyph_order_anomalies` catches
  this — a human has to read the extracted text. There is no automated check yet.
- **Cheaper models violate rules #1–#3 in new fields as document variety grows.** Four
  distinct fields were caught across only three documents. Targeted prompt fixes worked
  every time, but this is an ongoing tax, not a solved problem. Treat a validation crash as
  a finding to diagnose, never as a reason to loosen the schema.
- **Local venv is Python 3.9** (needs `eval_type_backport`); Docker runs 3.12. Keep
  `from __future__ import annotations` in every module or local runs break. This also means
  a module-level assignment like `X = Callable[[str | None], Y]` breaks on 3.9 even with the
  `__future__` import, because it's a real expression, not a deferred annotation — use
  `typing.Optional[str]` for anything evaluated at import time, not inside a signature.
- **`MAX_TOKENS = 8_000` (`app/llm/client.py`) is not a safe universal default.** Reasoning
  models spend a large, variable share of it on thinking before ever emitting the final JSON
  — confirmed live on both Gemini (thinking tokens 65–72% of total) and an OpenAI-compatible
  reasoning model (`openai/gpt-oss-120b` via Groq, which exhausted the whole budget mid-
  reasoning on a 5-field group and never produced JSON at all). Not raised globally without
  evidence Anthropic/OpenAI's own models need it — a reasoning-heavy model likely needs its
  own larger per-provider or per-group budget instead.
- **Provider usage/cost fields are provider-neutral (`cache_write_tokens`, `cached_read_tokens`),
  not Anthropic's names.** This was a deliberate breaking API-response change (see the
  multi-provider plan's Task 4) — `frontend/src/types/schema.ts` and `UsageFooter.tsx` were
  updated in the same commit as `schema.py`. If you see `cache_creation_input_tokens`
  anywhere outside `anthropic_provider.py` (where it's translating the raw Anthropic SDK
  response), that's a bug, not a stale name to leave alone — it happened twice already in
  `run_extraction.py` and `run_eval.py` during the same rewrite.
- **Building a JSON schema by hand for OpenAI-compatible strict mode needs two transforms
  Pydantic's `model_json_schema()` doesn't do for you**: `additionalProperties: false` on
  every object node (including nested models under `$defs`), and every property key must
  also appear in `required` (optionality is expressed as a nullable type, never an omittable
  key). The real `openai` SDK's `.parse()` does both automatically for OpenAI itself, which
  is why `openai_provider.py` never needed this and `openai_compat_provider.py` does — see
  `_make_strict_json_schema()` there. Confirmed against a real endpoint (Groq), not assumed.
- **Don't trust a remembered model name.** `gemini-2.5-flash` was deprecated between this
  project's plan being written and executed — the API's own 404 named the replacement. Model
  lineups move faster than any static knowledge; treat a live 404/400 naming a different
  model as authoritative over anything remembered.

## Working agreements specific to this repo

- **API calls cost real money.** Any extraction or eval run against a live provider spends
  the user's own key (a full 3-document eval has cost up to ~$3.75). Always confirm with the
  user before running one, and report the actual cost afterward.
- **Debug from evidence, not guesses.** When extraction fails, read the exact validation
  error, check the cited field against the real document text, and confirm the root cause
  before editing. Several bugs here looked identical on the surface and had different causes.
- **Report eval numbers as counts, not percentages** — the fixture set is 3 documents.
  Always include crashes and `missed`, not just `exact`.
- **Never commit `.env`, PDFs, or anything under `outputs/`** (`.gitignore` covers these).
  The user routes commits through the `/quick-commit` skill rather than direct `git commit`.

## Commands

```bash
# tests (must stay green)
cd backend && .venv/bin/python -m pytest tests/unit -q
cd frontend && npx tsc -b

# run the app: backend in Docker (:8000), frontend separately (:5173)
docker compose up -d --build        # backend only — there is no frontend Docker service
cd frontend && npm run dev

# diagnostics
cd backend && .venv/bin/python -m app.pdf.extract <pdf>   # can text be extracted at all?

# 💸 these spend real money — confirm with the user first
cd backend && set -a && source ../.env && set +a
.venv/bin/python -m app.run_extraction <pdf>
.venv/bin/python -m app.eval.run_eval --model <model>

# run/eval against a non-default provider: set TOR_PROVIDER first (reads
# from .env otherwise) — e.g. TOR_PROVIDER=openai, TOR_PROVIDER=gemini,
# or TOR_PROVIDER=openai_compat (also needs TOR_PROVIDER_BASE_URL)
TOR_PROVIDER=openai .venv/bin/python -m app.eval.run_eval --model <model>
```

## Licensing constraint

The project is **AGPL-3.0**, forced by the PyMuPDF dependency (AGPL-or-commercial). The
backend is a network service, so AGPL §13 applies: running a modified version as a service
obliges you to publish that version's source. Do not change the license, and flag it before
adding any dependency whose license conflicts — that decision is the owner's, not yours.
`python-docx` (DOCX ingestion) and `openpyxl` (XLSX ingestion, gated off — see below) were
both added and verified MIT against PyPI before being introduced.

## Provider architecture

Extraction goes through an `LLMProvider` port (`backend/app/llm/providers/base.py`), not
directly through any vendor SDK. `client.py` only knows this interface; it never imports
`anthropic`/`openai`/`google.genai` itself. Four adapters exist:

| Provider name | Adapter | Covers |
|---|---|---|
| `anthropic` | `anthropic_provider.py` | Claude (the original, most-tested path) |
| `openai` | `openai_provider.py` | GPT models on OpenAI's own API |
| `gemini` | `gemini_provider.py` | Google Gemini |
| `openai_compat` | `openai_compat_provider.py` | Any OpenAI-API-compatible endpoint — Ollama, vLLM, Together, Groq, OpenRouter, Fireworks. This is how Llama/Qwen/etc. are reached: they're models, not providers, and virtually every way to serve them speaks this protocol. |

`registry.get_provider(name, api_key=, base_url=, model=)` is the only way to construct one.
It enforces the operator rule that **native structured-output support is mandatory** — a
provider that can't enforce a schema at the API level is refused at construction time, not
mid-extraction. For `openai_compat` specifically, whether that's true depends on the serving
stack, not the model, so construction runs a real one-shot probe request rather than trusting
a static flag (see `OpenAICompatProvider._probe`).

Selection is env-var only (`TOR_PROVIDER`, `TOR_MODEL`), matching the "operator picks, not the
end user" design decision — see `.env.example` for the exact variable names per provider.
Per-group overrides (`TOR_GROUP_<GROUPNAME>=<provider>:<model>`) let one field group run on a
different provider/model than the document default — added specifically because cheaper
models were shown to violate rules #1–#3 more often on `qualifications`/`key_dates`/`misc`
than on the flat groups.

**Verified live, as of the migration:** `anthropic` (full pipeline, many runs). `openai` and
`gemini` adapters are built, registered, and unit-tested; their full 3-document eval gates
are blocked by account issues (no OpenAI billing credit; Gemini's free-tier daily quota),
not code problems — see `docs/plans/2026-09-02-multi-provider-migration.md` for exactly what
each one has and hasn't been verified against. `openai_compat` has been verified end-to-end
against a real hosted endpoint (Groq).

**Vision input (scanned PDF pages, no text layer):** `ProviderCapabilities.vision_input` is
`True` for `anthropic`/`openai`/`gemini` and `False` by default for `openai_compat` (opt in
with `TOR_OPENAI_COMPAT_VISION=1` — deliberately never auto-probed like structured output,
because a stack that silently ignores an image and answers from the caption text alone
produces schema-valid, plausible output with no way to detect it). Only `anthropic` has been
verified live with real image content (a real 16-page scanned document); the `openai`/
`gemini` message shapes for images are written to each SDK's documented API but have not
been run against a real call — treat them the same as their un-verified eval gates above.

## Where things are

- `PROGRESS.md` — session-to-session status: what's done, what's next, bugs found and fixed.
  Read it when picking up work; it is narrative and volatile, unlike this file.
- `docs/plans/2026-09-02-multi-provider-migration.md` — the multi-provider implementation
  plan, with per-step checkboxes kept honestly up to date (`[x]` done, `[~]` partially done
  with a note on what's left, `[ ]` not started) — check this before assuming a step is
  finished just because the feature exists.
- `backend/scripts/spike_provider.py` — throwaway-but-kept discovery script for confirming a
  new provider SDK's real method/field names against a live call before writing an adapter
  against a remembered API shape. Reuse this pattern for any 5th provider.
- `backend/app/llm/prompts/*.md` — extraction prompts. Prompt wording is load-bearing here;
  several were narrowed to fix real bugs, and the reasons are in `PROGRESS.md`.
- `backend/tests/fixtures/samples.json` — eval sample sources, including which candidates
  were rejected and why (scanned, garbled font, redundant).
