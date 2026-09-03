"""End-to-end CLI: PDF -> extracted text (Step 1) -> Claude extraction call
(Step 3) -> assembled TORDocument with derived fields, usage, and cost.

Usage:
    ANTHROPIC_API_KEY=... python -m app.run_extraction path/to/document.pdf [--model claude-haiku-4-5]

Writes the full result JSON to outputs/<pdf_stem>.json (gitignored) and
prints a human-readable summary including token usage and estimated cost.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import api_key_for_provider, load_config
from app.derive.calculations import assemble_document
from app.llm.client import ExtractionValidationError, extract
from app.llm.groups import FIELD_GROUPS, apply_group_overrides
from app.llm.providers.base import ProviderAPIError, ProviderAuthError, ProviderRateLimitError
from app.llm.providers.registry import get_provider
from app.pdf.extract import build_document_text, extract_document

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path")
    parser.add_argument("--model", default=None, help="override TOR_MODEL env var")
    args = parser.parse_args(argv)

    config = load_config()
    model = args.model or config.model

    if not config.api_key:
        print(
            f"error: no API key set for provider '{config.provider}'. Export it or put it "
            f"in backend/.env (see .env.example).",
            file=sys.stderr,
        )
        return 1

    print(f"กำลังดึงข้อความจาก {args.pdf_path} ...")
    result = extract_document(args.pdf_path)
    report = result.scan_report

    if report.usable_text_ratio == 0.0:
        print(
            "⚠️  เอกสารนี้ไม่มีข้อความให้ดึงเลยแม้แต่หน้าเดียว — "
            "นี่คือไฟล์สแกน ไม่รองรับใน v0.1 (ไม่มี OCR) จะไม่เรียก API",
            file=sys.stderr,
        )
        return 1

    print(
        f"พบข้อความใช้ได้ {report.usable_text_ratio:.0%} ของ {report.page_count} หน้า "
        f"({len(result.blocks)} text blocks) — กำลังเรียก Claude ({model}) ..."
    )
    if report.image_only_pages:
        print(f"  (หน้าที่ไม่มีข้อความ จะไม่ถูกส่งให้โมเดล: {[p.page_number for p in report.pages if p.status == 'image_only']})")

    document_text = build_document_text(result.blocks)

    provider = get_provider(config.provider, api_key=config.api_key, base_url=config.provider_base_url, model=model)
    groups = apply_group_overrides(FIELD_GROUPS, config.group_overrides)

    def _provider_for(name: str, override_model: str):
        # openai_compat hard-requires a base_url to construct at all, so an
        # override naming it must get the one configured base_url even when
        # it differs from the document default provider.
        base_url = config.provider_base_url if name in (config.provider, "openai_compat") else None
        return get_provider(name, api_key=api_key_for_provider(name), base_url=base_url, model=override_model)

    try:
        run = extract(
            document_text=document_text,
            provider=provider,
            model=model,
            groups=groups,
            provider_for=_provider_for,
        )
    except ExtractionValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ProviderAuthError:
        print(
            f"error: API key for provider '{config.provider}' is invalid — check it again",
            file=sys.stderr,
        )
        return 1
    except ProviderRateLimitError as exc:
        print(f"error: rate limited — {exc}", file=sys.stderr)
        return 1
    except ProviderAPIError as exc:
        print(f"error: provider API error — {exc}", file=sys.stderr)
        return 1

    doc = assemble_document(
        run.document,
        scan_report=report,
        provider=run.provider,
        model=run.model,
        usage=run.usage,
        duration_ms=run.duration_ms,
        cost=run.cost,
    )

    OUTPUTS_DIR.mkdir(exist_ok=True)
    out_path = OUTPUTS_DIR / f"{Path(args.pdf_path).stem}.json"
    out_path.write_text(doc.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")

    meta = doc.extraction_meta
    print("\n=== สรุปผล ===")
    print(f"  project_name : {doc.project_name.value!r}")
    print(f"  agency       : {doc.agency.value!r}")
    print(f"  budget_amount: {doc.budget_amount.value!r}")
    print(f"  median_price : {doc.median_price.value!r}")
    print(f"  key_dates    : {len(doc.key_dates)} รายการ")
    print(f"  risk_flags   : {len(doc.risk_flags)} รายการ")
    for flag in doc.risk_flags:
        print(f"    [{flag.origin}] {flag.text}")

    print("\n=== token usage & ค่าใช้จ่ายประมาณการ ===")
    u = meta.usage
    print(
        f"  input={u.input_tokens} output={u.output_tokens} "
        f"cache_write={u.cache_write_tokens} cache_read={u.cached_read_tokens}"
    )
    print(
        f"  ${meta.cost.usd:.4f} USD (~฿{meta.cost.thb:.2f} @ {meta.cost.usd_thb_rate} "
        f"ณ {meta.cost.rate_source_date}, ราคาโมเดลอ้างอิงวันที่ {meta.pricing_as_of})"
    )
    print(f"  duration: {meta.duration_ms} ms")
    print(f"\nบันทึกผลลัพธ์เต็มไว้ที่: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
