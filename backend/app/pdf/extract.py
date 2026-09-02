"""Step 1 CLI: PDF -> normalized Thai text blocks with page numbers,
plus a per-page scan/text-coverage report.

Usage:
    python -m app.pdf.extract path/to/document.pdf

This step deliberately does not touch the LLM or the frontend -- it exists
to prove (or disprove) the riskiest assumption in the whole project: that
text can be reliably extracted from real Thai government PDFs. See the
plan's "Real sample file inspection results" section for why this could not be assumed.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import fitz  # PyMuPDF

from app.pdf.scanned import DocumentScanReport, classify_document
from app.thai.normalize import GlyphAnomaly, find_glyph_order_anomalies, normalize_text

# PyMuPDF block_type: 0 = text, 1 = image
_TEXT_BLOCK_TYPE = 0


@dataclass
class TextBlock:
    page: int  # 1-indexed
    bbox: tuple[float, float, float, float]
    text: str  # normalized


@dataclass
class ExtractionResult:
    blocks: list[TextBlock]
    scan_report: DocumentScanReport
    anomalies: list[tuple[int, GlyphAnomaly]]  # (page_number, anomaly)


def extract_document(path: str) -> ExtractionResult:
    doc = fitz.open(path)
    try:
        return _extract_from_open_doc(doc)
    finally:
        doc.close()


def extract_document_from_bytes(data: bytes) -> ExtractionResult:
    """Same as extract_document, but from in-memory bytes -- used by the
    API upload endpoint so no temp file ever touches disk (keeps the
    backend stateless, per the plan's "not tied to a path on the machine" rule).
    """
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return _extract_from_open_doc(doc)
    finally:
        doc.close()


def _extract_from_open_doc(doc: "fitz.Document") -> ExtractionResult:
    blocks: list[TextBlock] = []
    anomalies: list[tuple[int, GlyphAnomaly]] = []

    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        raw_blocks = page.get_text("blocks")
        for b in raw_blocks:
            x0, y0, x1, y1, text, _block_no, block_type = b[:7]
            if block_type != _TEXT_BLOCK_TYPE:
                continue
            if not text or not text.strip():
                continue
            normalized = normalize_text(text)
            blocks.append(TextBlock(page=page_number, bbox=(x0, y0, x1, y1), text=normalized))
            for anomaly in find_glyph_order_anomalies(normalized):
                anomalies.append((page_number, anomaly))

    scan_report = classify_document(doc)
    return ExtractionResult(blocks=blocks, scan_report=scan_report, anomalies=anomalies)


def build_document_text(blocks: list[TextBlock]) -> str:
    """Concatenate text blocks into one page-marked string for the LLM
    prompt. Shared by the CLI (run_extraction.py) and the API endpoint.
    """
    lines: list[str] = []
    current_page: int | None = None
    for block in blocks:
        if block.page != current_page:
            current_page = block.page
            lines.append(f"\n[หน้า {current_page}]")
        lines.append(block.text)
    return "\n".join(lines)


def _print_summary(path: str, result: ExtractionResult) -> None:
    report = result.scan_report

    print(f"=== {path} ===")
    print(f"หน้าทั้งหมด: {report.page_count}")
    print(
        f"  text: {report.text_pages}  |  mixed: {report.mixed_pages}  |  "
        f"image_only: {report.image_only_pages}"
    )
    print(f"  สัดส่วนหน้าที่มีข้อความใช้ได้ (text+mixed): {report.usable_text_ratio:.0%}")

    image_only_pages = [p.page_number for p in report.pages if p.status == "image_only"]
    if image_only_pages:
        print(f"  หน้าที่ไม่มีข้อความเลย (image_only): {image_only_pages}")

    if report.page_count > 0 and report.usable_text_ratio == 0.0:
        print(
            "  ⚠️  ไม่พบข้อความในเอกสารนี้เลยแม้แต่หน้าเดียว — "
            "นี่คือไฟล์สแกน ไม่รองรับใน v0.1 (ไม่มี OCR)"
        )

    fonts_missing = report.all_fonts_without_tounicode
    if fonts_missing:
        print(f"\n  ฟอนต์ที่ไม่มี /ToUnicode CMap ({len(fonts_missing)} ฟอนต์):")
        for f in fonts_missing[:15]:
            print(f"    - {f}")
        print(
            "    (ฟอนต์เหล่านี้เสี่ยงให้สระ/วรรณยุกต์เพี้ยน — "
            "NFC normalization แก้ปัญหานี้ไม่ได้)"
        )

    print(f"\nจำนวน text block ที่ดึงได้: {len(result.blocks)}")
    print("ตัวอย่างข้อความ (10 บรรทัดแรกที่ไม่ว่าง):")
    shown = 0
    for block in result.blocks:
        for line in block.text.splitlines():
            line = line.strip()
            if not line:
                continue
            print(f"  [p.{block.page}] {line}")
            shown += 1
            if shown >= 10:
                break
        if shown >= 10:
            break
    if shown == 0:
        print("  (ไม่มีข้อความให้แสดง)")

    if result.anomalies:
        print(f"\n⚠️  พบจุดที่ตัวอักษรอาจเรียงผิดลำดับ {len(result.anomalies)} จุด ตัวอย่าง:")
        for page_number, anomaly in result.anomalies[:15]:
            print(f"  [p.{page_number}] {anomaly.reason}")
            print(f"           context: {anomaly.context!r}")
    else:
        print("\nไม่พบสัญญาณสระ/วรรณยุกต์เรียงผิดลำดับจากการตรวจเบื้องต้น")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="path to a PDF file")
    args = parser.parse_args(argv)

    try:
        result = extract_document(args.pdf_path)
    except Exception as exc:  # noqa: BLE001 - CLI top-level, report and exit non-zero
        print(f"error: failed to process {args.pdf_path}: {exc}", file=sys.stderr)
        return 1

    _print_summary(args.pdf_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
