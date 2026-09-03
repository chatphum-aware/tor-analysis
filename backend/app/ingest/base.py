"""Format-neutral ingestion port: bytes in, one flat marked-up text string
plus format metadata out.

This exists because `api/extract.py`, `run_extraction.py`, `eval/run_eval.py`
and `eval/compare_providers.py` all called `app.pdf.extract` directly. Adding
DOCX and XLSX as one-off paths would have meant re-deciding "what does
document_text look like, what metadata do we report" at every one of those
call sites, once per format. They now depend on this shape instead, so a new
format is one new module plus one registry entry.

The PDF implementation is a thin facade over the existing, well-tested
`app/pdf/extract.py` + `app/pdf/scanned.py` -- deliberately composed, not
rewritten, because the PDF path is the only one proven against real
documents and a refactor of it would risk the one thing that works.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.models.schema import DocumentKind, SourcePreview


class UnsupportedDocumentError(RuntimeError):
    """Raised when bytes match no format we can ingest. Carries the head
    bytes so a caller can say something more useful than "bad file"."""

    def __init__(self, filename: Optional[str], head: bytes) -> None:
        self.filename = filename
        self.head = head
        super().__init__(
            f"unrecognized document format"
            f"{f' for {filename!r}' if filename else ''} (first bytes: {head!r})"
        )


class UnsupportedKindError(RuntimeError):
    """The format was recognized, but there's no ingestor for it yet. Kept
    separate from UnsupportedDocumentError so callers can say "we know this is
    a DOCX, we just can't read it yet" instead of "unrecognized file", which
    would be actively misleading."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(f"no ingestor registered for document kind {kind!r}")


@dataclass
class RenderedPageImage:
    """A PDF page rasterized for a vision model. Raw bytes, not base64 --
    each provider adapter encodes it the way its own SDK wants."""

    page: int
    media_type: str  # "image/png"
    data: bytes


@dataclass
class IngestMeta:
    """What we can say about the source document's structure.

    Every field beyond `document_kind` is optional because the formats
    genuinely disagree about what exists: a spreadsheet has no pages, a
    Word file has no page count that isn't a rendering artifact, and a PDF
    has no sheet names. A null here means "not applicable to this format",
    which `document_kind` already explains -- so unlike rule #3's null
    values, it needs no separate reason.
    """

    document_kind: DocumentKind
    # pdf only
    page_count: Optional[int] = None
    usable_text_page_ratio: Optional[float] = None
    image_only_pages: Optional[List[int]] = None
    # docx only
    paragraph_count: Optional[int] = None
    # xlsx only
    sheet_names: Optional[List[str]] = None


@dataclass
class IngestedDocument:
    document_text: str
    meta: IngestMeta
    # Structure the frontend needs to render + highlight a citation, for
    # formats the browser can't render itself. None for PDFs, which the
    # browser renders from the user's own file via react-pdf.
    preview: Optional[SourcePreview] = None
    # Non-empty only for PDFs with scanned pages, once vision lands. DOCX and
    # XLSX always have a real text/cell layer, so they never populate this.
    images: List[RenderedPageImage] = field(default_factory=list)
