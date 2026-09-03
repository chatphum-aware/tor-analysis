"""Cross-provider comparison for the TOR extraction eval.

Two modes:
  --check-schema-ceiling  one cheap call per FieldGroup, reporting which
                          group schemas this provider will even accept. The
                          6-way split exists because of an Anthropic limit
                          ("compiled grammar is too large"); every provider
                          has its own ceiling, and discovering it per group
                          up front is far cheaper than hitting it mid-run.
                          Note: a rejection here means the schema itself was
                          refused (grammar-too-complex style errors). A
                          separate, real failure mode -- a reasoning model
                          truncating mid-thought before ever emitting JSON --
                          looks similar (also an exception) but is a token
                          budget problem, not a schema-ceiling problem; the
                          per-group error text distinguishes the two.
  --eval                  full eval per provider, emitting one markdown table
                          so accuracy and cost are compared side by side.

Usage:
    python -m app.eval.compare_providers --check-schema-ceiling --provider openai --model <id>
    python -m app.eval.compare_providers --eval \\
        --provider anthropic --model claude-opus-5 \\
        --provider openai_compat --model <id>

Costs real money for every provider/model pair given to either mode.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

from app.config import api_key_for_provider, load_config
from app.derive.calculations import assemble_document
from app.derive.pricing import Cost, Usage, compute_cost
from app.eval.run_eval import EXPECTED_DIR, SAMPLES_DIR, FieldTally, _merge, score_document
from app.llm.client import ExtractionValidationError, extract
from app.llm.groups import FIELD_GROUPS
from app.llm.providers.base import ProviderError, SystemBlock
from app.llm.providers.registry import get_provider
from app.ingest.pdf_ingest import ingest_pdf_path

_STUB_DOCUMENT = "[หน้า 1]\nเอกสารทดสอบ ไม่มีเนื้อหาจริง ใช้สำหรับตรวจสอบ schema เท่านั้น\n"

# Confirmed live (2026-09-02): 512 is too small to tell "schema rejected
# outright" apart from "ran out of budget writing a verbose all-null
# response". A stub document with no real content still means every leaf
# field gets a null+reason -- and reason text scales with how many fields
# a group has, NOT with whether the schema itself was too complex. This
# produced false REJECTED/FAILED results on Anthropic (a non-reasoning
# model) for basic_info/bonds/misc, which are the project's ordinary
# groups that already work fine in production at MAX_TOKENS=8000. Raised
# so a real schema-complexity rejection (an immediate 400 before any
# generation starts) isn't confused with plain truncation.
_CEILING_CHECK_MAX_TOKENS = 3000


def check_schema_ceiling(provider_name: str, model: str, base_url: str | None) -> None:
    provider = get_provider(
        provider_name, api_key=api_key_for_provider(provider_name), base_url=base_url, model=model
    )
    print(f"provider={provider_name} model={model}")
    for group in FIELD_GROUPS:
        try:
            provider.complete_structured(
                system_blocks=[SystemBlock(text=_STUB_DOCUMENT, cacheable=True)],
                user_message=f"สกัดข้อมูลกลุ่ม '{group.name}' ตาม schema ให้ครบทุกฟิลด์",
                schema=group.schema,
                model=model,
                max_tokens=_CEILING_CHECK_MAX_TOKENS,
            )
        except ProviderError as exc:
            print(f"  {group.name}: REJECTED -- {exc}")
        except Exception as exc:  # noqa: BLE001 -- report any failure, don't crash the sweep
            print(f"  {group.name}: FAILED -- {type(exc).__name__}: {exc}")
        else:
            print(f"  {group.name}: OK")


@dataclass
class ProviderEvalSummary:
    provider: str
    model: str
    tallies: dict[str, FieldTally]
    crashed_documents: list[str]
    cost: Cost | None


def run_eval_for_provider(provider_name: str, model: str, base_url: str | None) -> ProviderEvalSummary:
    provider = get_provider(
        provider_name, api_key=api_key_for_provider(provider_name), base_url=base_url, model=model
    )
    total_tallies: dict[str, FieldTally] = {}
    crashed: list[str] = []
    total_usage = Usage(0, 0, 0, 0)

    for expected_path in sorted(EXPECTED_DIR.glob("*.json")):
        sample_id = expected_path.stem
        pdf_path = SAMPLES_DIR / f"{sample_id}.pdf"
        if not pdf_path.exists():
            print(f"  skip {sample_id}: {pdf_path} not found", file=sys.stderr)
            continue

        print(f"  extracting {sample_id} ({provider_name}/{model}) ...")
        ingested = ingest_pdf_path(str(pdf_path))
        document_text = ingested.document_text
        try:
            run = extract(
                document_text=document_text, provider=provider, model=model, groups=FIELD_GROUPS
            )
        except (ExtractionValidationError, ProviderError) as exc:
            print(f"    CRASHED: {exc}", file=sys.stderr)
            crashed.append(sample_id)
            continue

        doc = assemble_document(
            run.document,
            ingest_meta=ingested.meta,
            provider=provider_name,
            model=run.model,
            usage=run.usage,
            duration_ms=run.duration_ms,
        )
        actual = json.loads(doc.model_dump_json(exclude={"extraction_meta"}))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        tallies, _mismatches, _rf = score_document(expected, actual)
        _merge(total_tallies, tallies)

        total_usage.input_tokens += run.usage.input_tokens
        total_usage.output_tokens += run.usage.output_tokens
        total_usage.cache_write_tokens += run.usage.cache_write_tokens
        total_usage.cached_read_tokens += run.usage.cached_read_tokens

    cost = compute_cost(provider_name, model, total_usage)
    return ProviderEvalSummary(
        provider=provider_name, model=model, tallies=total_tallies, crashed_documents=crashed, cost=cost
    )


def render_comparison(summaries: list[ProviderEvalSummary]) -> str:
    lines = [
        "# Cross-provider eval comparison",
        "",
        "Counts, not percentages -- n=3 documents is too small to honestly claim a %.",
        "A provider that crashed on a document contributes 0 fields from it, which can make "
        "its row look artificially clean -- always read the Crashed column alongside Exact.",
        "",
        "| Provider/Model | Exact | Wrong | Missed | Hallucinated | Crashed docs | Cost (USD) |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        grand = FieldTally()
        for t in s.tallies.values():
            grand.exact += t.exact
            grand.wrong += t.wrong
            grand.missed += t.missed
            grand.hallucinated += t.hallucinated
        crashed = ", ".join(s.crashed_documents) if s.crashed_documents else "none"
        cost_str = f"${s.cost.usd:.4f}" if s.cost is not None else "unknown"
        lines.append(
            f"| {s.provider}/{s.model} | {grand.exact} | {grand.wrong} | {grand.missed} | "
            f"{grand.hallucinated} | {crashed} | {cost_str} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-schema-ceiling", action="store_true")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--provider", action="append", default=[])
    parser.add_argument("--model", action="append", default=[])
    args = parser.parse_args(argv)

    if args.check_schema_ceiling == args.eval:
        print("error: pass exactly one of --check-schema-ceiling or --eval", file=sys.stderr)
        return 1
    if len(args.provider) != len(args.model) or not args.provider:
        print("error: pass matching --provider/--model pairs (at least one)", file=sys.stderr)
        return 1

    config = load_config()

    if args.check_schema_ceiling:
        for provider_name, model in zip(args.provider, args.model):
            check_schema_ceiling(provider_name, model, config.provider_base_url)
        return 0

    summaries = [
        run_eval_for_provider(provider_name, model, config.provider_base_url)
        for provider_name, model in zip(args.provider, args.model)
    ]
    print()
    print(render_comparison(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
