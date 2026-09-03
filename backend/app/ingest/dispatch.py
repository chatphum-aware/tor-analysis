"""One place that maps a detected format to its ingestor.

Both the API endpoint and the CLI go through here, so adding a format is one
registry entry rather than an edit in every caller -- which was the whole
point of introducing this layer.

XLSX is implemented and unit-tested but **disabled by default**. Reason, so
nobody re-enables it by accident and nobody deletes it as dead code either:
a survey for real Thai government TOR documents in .xlsx found none. Thai
procurement TORs come out of e-GP as PDF and circulate as DOC/DOCX; Excel
shows up as *attachments* (BOQ, price breakdowns, ราคากลาง sheets) whose
content doesn't map onto this tool's TOR schema -- extracting one would
honestly return mostly nulls. The code stays because it proved the
format-neutral ingest layer works for a genuinely non-PDF format, and it can
be switched on with TOR_ENABLE_XLSX=1 the moment a real one turns up (it has
NOT been verified against a live model run -- see PROGRESS.md).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict

from app.ingest.base import IngestedDocument, UnsupportedKindError
from app.ingest.detect import sniff_document_kind
from app.ingest.docx_ingest import ingest_docx_bytes
from app.ingest.pdf_ingest import ingest_pdf_bytes
from app.ingest.xlsx_ingest import ingest_xlsx_bytes

_ALL_INGESTORS: Dict[str, Callable[[bytes], IngestedDocument]] = {
    "pdf": ingest_pdf_bytes,
    "docx": ingest_docx_bytes,
    "xlsx": ingest_xlsx_bytes,
}

# Formats behind a flag, and the env var that enables each.
_FLAGGED_KINDS: Dict[str, str] = {"xlsx": "TOR_ENABLE_XLSX"}

_TRUTHY = {"1", "true", "yes", "on"}


def _is_enabled(kind: str) -> bool:
    env_var = _FLAGGED_KINDS.get(kind)
    if env_var is None:
        return True
    # Read at call time, not import time, so the flag can be flipped by
    # config/tests without reimporting the module.
    return os.environ.get(env_var, "").strip().lower() in _TRUTHY


def supported_kinds() -> tuple[str, ...]:
    """Kinds this deployment will actually ingest right now."""
    return tuple(k for k in _ALL_INGESTORS if _is_enabled(k))


def ingest_as(kind: str, data: bytes) -> IngestedDocument:
    """Ingest bytes already known to be `kind`. Split from ingest_bytes so a
    caller that wants to report *which* parser failed can sniff first and
    handle the parse error separately from the format error."""
    ingestor = _ALL_INGESTORS.get(kind)
    if ingestor is None or not _is_enabled(kind):
        raise UnsupportedKindError(kind)
    return ingestor(data)


def ingest_bytes(data: bytes, filename: str | None = None) -> IngestedDocument:
    """Raises UnsupportedDocumentError (unrecognized bytes) or
    UnsupportedKindError (recognized, but not enabled/supported)."""
    return ingest_as(sniff_document_kind(data, filename), data)


def ingest_path(path: str) -> IngestedDocument:
    p = Path(path)
    return ingest_bytes(p.read_bytes(), p.name)
