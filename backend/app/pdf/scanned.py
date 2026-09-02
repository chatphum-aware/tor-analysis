"""Per-page scanned/text detection.

The plan's key finding from real CGD sample files: a document is not
cleanly "scanned" or "text" -- a 77-page real-world TOR had both a genuine
text layer AND 64 embedded images (signed/stamped pages, drawings). A
single document-level `is_scanned` boolean either rejects a document that
is mostly usable, or silently accepts one whose content the model can't
actually see -- and the project's hard rule forbids returning an empty
result. So classification happens per page.

Also checks each page's fonts for a `/ToUnicode` CMap: fonts without one
have no reliable glyph->Unicode mapping, which is the direct mechanical
cause of scrambled Thai vowels/tone marks (NFC normalization cannot fix a
missing ToUnicode map -- the data is wrong before normalization ever runs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import fitz  # PyMuPDF

PageStatus = Literal["text", "mixed", "image_only"]

# A page with fewer extracted characters than this is treated as having no
# usable text layer, regardless of image content.
_MIN_TEXT_CHARS = 20
# Image coverage ratio above which a page is considered image-heavy.
_HIGH_IMAGE_COVERAGE = 0.5
_SOME_IMAGE_COVERAGE = 0.3


@dataclass
class PageReport:
    page_number: int  # 1-indexed
    status: PageStatus
    text_char_count: int
    image_coverage_ratio: float
    fonts_without_tounicode: list[str] = field(default_factory=list)


@dataclass
class DocumentScanReport:
    page_count: int
    pages: list[PageReport]

    @property
    def text_pages(self) -> int:
        return sum(1 for p in self.pages if p.status == "text")

    @property
    def mixed_pages(self) -> int:
        return sum(1 for p in self.pages if p.status == "mixed")

    @property
    def image_only_pages(self) -> int:
        return sum(1 for p in self.pages if p.status == "image_only")

    @property
    def usable_text_ratio(self) -> float:
        """Fraction of pages that have *any* extractable text (text + mixed)."""
        if self.page_count == 0:
            return 0.0
        return (self.text_pages + self.mixed_pages) / self.page_count

    @property
    def all_fonts_without_tounicode(self) -> list[str]:
        seen: dict[str, None] = {}
        for p in self.pages:
            for f in p.fonts_without_tounicode:
                seen[f] = None
        return list(seen.keys())


def _image_coverage_ratio(page: "fitz.Page") -> float:
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return 0.0
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:
        return 0.0
    covered = 0.0
    for info in infos:
        bbox = info.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        covered += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return min(1.0, covered / page_area)


def _fonts_without_tounicode(doc: "fitz.Document", page: "fitz.Page") -> list[str]:
    missing: list[str] = []
    try:
        fonts = page.get_fonts(full=True)
    except Exception:
        return missing
    for f in fonts:
        xref, _ext, _ftype, basefont = f[0], f[1], f[2], f[3]
        try:
            obj = doc.xref_object(xref, compressed=False)
        except Exception:
            continue
        if "/ToUnicode" not in obj:
            missing.append(basefont)
    return missing


def _classify(text_chars: int, image_ratio: float) -> PageStatus:
    has_text = text_chars >= _MIN_TEXT_CHARS
    if has_text and image_ratio < _SOME_IMAGE_COVERAGE:
        return "text"
    if has_text and image_ratio >= _SOME_IMAGE_COVERAGE:
        return "mixed"
    if not has_text and image_ratio >= _HIGH_IMAGE_COVERAGE:
        return "image_only"
    # No text and no significant image coverage either (e.g. a blank page,
    # or a vector-drawing-only page). Conservatively treat as image_only --
    # there is no text for the model to read either way.
    return "image_only"


def classify_document(doc: "fitz.Document") -> DocumentScanReport:
    pages: list[PageReport] = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        text_chars = len(text.strip())
        image_ratio = _image_coverage_ratio(page)
        status = _classify(text_chars, image_ratio)
        fonts_missing = _fonts_without_tounicode(doc, page)
        pages.append(
            PageReport(
                page_number=i + 1,
                status=status,
                text_char_count=text_chars,
                image_coverage_ratio=round(image_ratio, 3),
                fonts_without_tounicode=fonts_missing,
            )
        )
    return DocumentScanReport(page_count=len(pages), pages=pages)
