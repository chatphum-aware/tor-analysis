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

import anthropic

from app.config import load_config
from app.derive.calculations import assemble_document
from app.llm.client import ExtractionValidationError, extract
from app.llm.groups import FIELD_GROUPS
from app.pdf.extract import build_document_text, extract_document

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path")
    parser.add_argument("--model", default=None, help="override TOR_MODEL env var")
    args = parser.parse_args(argv)

    config = load_config()
    model = args.model or config.model

    if not config.anthropic_api_key:
        print(
            "error: ANTHROPIC_API_KEY is not set. Export it or put it in backend/.env "
            "(see .env.example).",
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

    try:
        run = extract(
            document_text=document_text,
            api_key=config.anthropic_api_key,
            model=model,
            groups=FIELD_GROUPS,
        )
    except ExtractionValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except anthropic.AuthenticationError:
        print("error: ANTHROPIC_API_KEY ไม่ถูกต้อง (401) — ตรวจสอบ key อีกครั้ง", file=sys.stderr)
        return 1
    except anthropic.RateLimitError as exc:
        print(f"error: rate limited (429) — {exc}", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as exc:
        print(f"error: Claude API error ({exc.status_code}) — {exc.message}", file=sys.stderr)
        return 1

    doc = assemble_document(
        run.document,
        scan_report=report,
        model=run.model,
        usage=run.usage,
        duration_ms=run.duration_ms,
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
        f"cache_write={u.cache_creation_input_tokens} cache_read={u.cache_read_input_tokens}"
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
