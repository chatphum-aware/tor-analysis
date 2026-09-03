"""Which format is this? Decided by magic bytes, never by filename.

The extension is used only in error messages. Trusting it for dispatch would
mean a file renamed to .pdf gets handed to the PDF parser and fails with a
confusing "couldn't open PDF" error, and -- worse -- a .docx renamed to .pdf
would silently take a path that can't read it. The bytes are the only
authority on what a file actually is.
"""
from __future__ import annotations

import io
import zipfile

from app.ingest.base import DocumentKind, UnsupportedDocumentError

_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"

# DOCX and XLSX are both OOXML: a zip whose entry names say which it is.
_OOXML_MARKERS: tuple[tuple[str, DocumentKind], ...] = (
    ("word/document.xml", "docx"),
    ("xl/workbook.xml", "xlsx"),
)


def sniff_document_kind(data: bytes, filename: str | None = None) -> DocumentKind:
    if data[:4] == _PDF_MAGIC:
        return "pdf"
    if data[:4] == _ZIP_MAGIC:
        return _sniff_ooxml_kind(data, filename)
    raise UnsupportedDocumentError(filename, data[:16])


def _sniff_ooxml_kind(data: bytes, filename: str | None) -> DocumentKind:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        # Has the zip magic but isn't a readable zip -- truncated or corrupt.
        raise UnsupportedDocumentError(filename, data[:16]) from exc
    for marker, kind in _OOXML_MARKERS:
        if marker in names:
            return kind
    # A valid zip, just not an Office document (e.g. a plain .zip).
    raise UnsupportedDocumentError(filename, data[:16])
