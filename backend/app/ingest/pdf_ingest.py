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
"""
from __future__ import annotations

from app.ingest.base import IngestedDocument, IngestMeta
from app.pdf.extract import (
    ExtractionResult,
    build_document_text,
    extract_document,
    extract_document_from_bytes,
)
from app.pdf.scanned import DocumentScanReport


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


def _to_ingested(result: ExtractionResult) -> IngestedDocument:
    return IngestedDocument(
        document_text=build_document_text(result.blocks),
        meta=ingest_meta_from_scan_report(result.scan_report),
        images=[],  # vision rendering lands in a later phase
    )


def ingest_pdf_bytes(data: bytes) -> IngestedDocument:
    return _to_ingested(extract_document_from_bytes(data))


def ingest_pdf_path(path: str) -> IngestedDocument:
    return _to_ingested(extract_document(path))
