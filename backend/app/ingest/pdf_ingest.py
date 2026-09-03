"""PDF ingestion: a facade over app/pdf/extract.py and app/pdf/scanned.py.

Composition on purpose, not a rewrite. The PDF path is the only one verified
against real Thai government documents (3-fixture eval, zero crashes), so the
extraction and page-classification logic underneath is left exactly as it is;
this module only adapts its output to the format-neutral `IngestedDocument`
shape that every caller now depends on.

`document_text` here is byte-identical to what `build_document_text` produced
before this layer existed -- the `[หน้า N]` markers are what let the model
cite a page number in `Source.page`, so changing them would silently break
every citation.

Image rendering (for scanned pages, added for vision-based OCR): PyMuPDF is
imported directly here rather than adding a second responsibility to
app/pdf/extract.py -- `extract_document`/`extract_document_from_bytes` close
their `fitz.Document` before returning (by design, so a caller never holds a
PyMuPDF handle open), so rasterizing has to reopen the file. This costs a
second parse only for documents that actually have image_only pages, which
matches this module's existing "don't touch the proven path" principle: the
common all-text case is completely unaffected.
"""
from __future__ import annotations

import os
from typing import Callable, List

import fitz  # PyMuPDF

from app.ingest.base import IngestedDocument, IngestMeta, RenderedPageImage
from app.pdf.extract import (
    ExtractionResult,
    build_document_text,
    extract_document,
    extract_document_from_bytes,
)
from app.pdf.scanned import DocumentScanReport

# A pathological document could otherwise send dozens of full-page images to
# a paid vision model with no warning -- `scanned.py`'s own docstring cites a
# real 77-page document with 64 embedded images. Refusing loudly past this
# cap is rule #5's "never silently return a partial/crippled result" applied
# to ingestion: dropping pages past a cap would make their content look
# genuinely absent rather than merely unread.
MAX_VISION_PAGES = int(os.environ.get("TOR_MAX_VISION_PAGES", "20"))

# JPEG, not PNG: confirmed live against a real 16-page scanned document that
# PNG at 200 DPI is not a safe default -- it produced ~55MB of base64 image
# data and Anthropic rejected the request outright with a 413 before even
# checking the API key. Scanned pages are photo-like (scanner noise, no flat
# color regions), which is exactly the content PNG's lossless compression
# handles worst; JPEG cuts that same page to roughly a sixth of the size.
# Quality 70 and 150 DPI were chosen empirically against that document (see
# PROGRESS.md) to leave real margin under provider request-size limits while
# keeping Thai text legible -- not yet validated against extraction ACCURACY
# on a variety of scan quality, only against payload size.
VISION_RENDER_DPI = int(os.environ.get("TOR_VISION_DPI", "150"))
VISION_JPEG_QUALITY = int(os.environ.get("TOR_VISION_JPEG_QUALITY", "70"))

# Defense in depth alongside MAX_VISION_PAGES: a page-count cap doesn't bound
# a single unusually dense/large page, and page count wasn't even what broke
# on the real document above (16 pages is under MAX_VISION_PAGES=20; the
# bytes were the actual problem). Comfortably under every major provider's
# published per-request limit (Anthropic's is 32MB) with room for the prompt
# text alongside the images.
MAX_VISION_PAYLOAD_BYTES = int(os.environ.get("TOR_MAX_VISION_PAYLOAD_BYTES", str(20 * 1024 * 1024)))


class TooManyVisionPagesError(RuntimeError):
    """Raised instead of silently truncating -- see MAX_VISION_PAGES and
    MAX_VISION_PAYLOAD_BYTES above."""


def ingest_meta_from_scan_report(report: DocumentScanReport) -> IngestMeta:
    """The PDF-shaped subset of IngestMeta. Split out so tests and any caller
    holding only a scan report can build the same metadata the real ingestion
    path does, rather than hand-assembling it and drifting."""
    return IngestMeta(
        document_kind="pdf",
        page_count=report.page_count,
        usable_text_page_ratio=round(report.usable_text_ratio, 4),
        image_only_pages=[p.page_number for p in report.pages if p.status == "image_only"],
        paragraph_count=None,
        sheet_names=None,
    )


def _render_pages(
    open_doc: Callable[[], "fitz.Document"], page_numbers: List[int]
) -> List[RenderedPageImage]:
    if len(page_numbers) > MAX_VISION_PAGES:
        raise TooManyVisionPagesError(
            f"เอกสารนี้มีหน้าที่เป็นภาพสแกน (ไม่มีข้อความ) {len(page_numbers)} หน้า "
            f"ซึ่งเกิน {MAX_VISION_PAGES} หน้าที่เครื่องมือนี้อ่านด้วย vision ได้ในครั้งเดียว — "
            f"กรุณาแยกเฉพาะส่วนที่เกี่ยวข้องแล้วอัปโหลดใหม่"
        )
    doc = open_doc()
    try:
        images = [
            RenderedPageImage(
                page=n,
                media_type="image/jpeg",
                data=doc[n - 1].get_pixmap(dpi=VISION_RENDER_DPI).tobytes(
                    "jpeg", jpg_quality=VISION_JPEG_QUALITY
                ),
            )
            for n in page_numbers
        ]
    finally:
        doc.close()

    # Page COUNT alone doesn't bound total size -- confirmed live: a real
    # 16-page document (under MAX_VISION_PAGES=20) still produced a request
    # Anthropic rejected outright at 200 DPI/PNG. Checked after rendering,
    # not estimated beforehand, so the number is exact rather than guessed.
    total_bytes = sum(len(img.data) for img in images)
    if total_bytes > MAX_VISION_PAYLOAD_BYTES:
        raise TooManyVisionPagesError(
            f"ภาพหน้าเอกสารที่สแกนทั้งหมด {len(images)} หน้า มีขนาดรวม "
            f"{total_bytes / 1_048_576:.1f} MB ซึ่งเกินขนาดที่ส่งให้โมเดลได้ในครั้งเดียว "
            f"({MAX_VISION_PAYLOAD_BYTES / 1_048_576:.0f} MB) — "
            f"กรุณาแยกเฉพาะส่วนที่เกี่ยวข้องแล้วอัปโหลดใหม่"
        )
    return images


def _to_ingested(result: ExtractionResult, open_doc: Callable[[], "fitz.Document"]) -> IngestedDocument:
    meta = ingest_meta_from_scan_report(result.scan_report)
    # Only image_only pages get rendered -- a mixed page already contributes
    # real extracted text (see api/extract.py's per-page branching), and
    # speculatively also vision-rendering it is deferred until evidence shows
    # its text is missing content that's actually in an embedded image.
    images = _render_pages(open_doc, meta.image_only_pages) if meta.image_only_pages else []
    return IngestedDocument(
        document_text=build_document_text(result.blocks),
        meta=meta,
        images=images,
    )


def ingest_pdf_bytes(data: bytes) -> IngestedDocument:
    return _to_ingested(
        extract_document_from_bytes(data), lambda: fitz.open(stream=data, filetype="pdf")
    )


def ingest_pdf_path(path: str) -> IngestedDocument:
    return _to_ingested(extract_document(path), lambda: fitz.open(path))
