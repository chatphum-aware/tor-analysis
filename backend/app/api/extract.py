"""POST /api/extract -- upload one PDF, get back the full TORDocument.

Stateless by design (see the plan's "Online-ready" section): the response
IS the full result. There is no server-side storage and no result id --
the frontend already has everything it needs (JSON export is just saving
this response; CSV export posts it to /api/export/csv for reformatting).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import api_key_for_provider, load_config
from app.derive.calculations import assemble_document
from app.ingest.base import UnsupportedDocumentError, UnsupportedKindError
from app.ingest.detect import sniff_document_kind
from app.ingest.dispatch import ingest_as, supported_kinds
from app.ingest.docx_ingest import DocxTooLargeError
from app.ingest.pdf_ingest import TooManyVisionPagesError
from app.ingest.xlsx_ingest import XlsxTooLargeError
from app.llm.client import ExtractionValidationError, extract as llm_extract
from app.llm.groups import FIELD_GROUPS, apply_group_overrides
from app.llm.providers.base import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnsupportedError,
)
from app.llm.providers.registry import get_provider
from app.models.schema import TORDocument

router = APIRouter()

_FORMAT_LABELS_TH = {"pdf": "ไฟล์ PDF", "xlsx": "ไฟล์ Excel (.xlsx)", "docx": "ไฟล์ Word (.docx)"}


def _supported_formats_th() -> str:
    """Built from the enabled set, so the error can never promise a format
    this deployment has turned off (see ingest/dispatch.py)."""
    return " และ ".join(_FORMAT_LABELS_TH.get(k, k.upper()) for k in supported_kinds())


@router.post("/api/extract", response_model=TORDocument)
async def extract_endpoint(file: UploadFile = File(...)) -> TORDocument:
    config = load_config()
    if not config.api_key:
        raise HTTPException(
            status_code=500,
            detail=f"ยังไม่ได้ตั้งค่า API key ของ provider '{config.provider}' บนเซิร์ฟเวอร์",
        )

    max_bytes = config.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"ไฟล์ใหญ่เกิน {config.max_upload_mb} MB")
    if not data:
        raise HTTPException(status_code=400, detail="ไฟล์ว่างเปล่า")

    # Format is decided by magic bytes, never the filename -- see ingest/detect.py.
    try:
        kind = sniff_document_kind(data, file.filename)
    except UnsupportedDocumentError:
        raise HTTPException(
            status_code=415,
            detail=f"รูปแบบไฟล์นี้ไม่รองรับ — รองรับเฉพาะ {_supported_formats_th()}",
        ) from None

    try:
        ingested = ingest_as(kind, data)
    except UnsupportedKindError as exc:
        # Recognized the format, just can't read it yet -- say which one.
        raise HTTPException(
            status_code=415,
            detail=f"ยังไม่รองรับไฟล์ {exc.kind.upper()} — รองรับเฉพาะ {_supported_formats_th()}",
        ) from None
    except (XlsxTooLargeError, DocxTooLargeError, TooManyVisionPagesError) as exc:
        # Same family: the file was read successfully but exceeds a bound
        # this tool refuses to silently truncate past (rule #5's "never
        # return a partial result quietly", applied to ingestion).
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001 - any parser open/parse failure -> 400
        # Format was recognized, so this is a broken file, not a wrong one.
        raise HTTPException(
            status_code=400, detail=f"เปิดไฟล์ {kind.upper()} ไม่ได้: {exc}"
        ) from None

    # A scanned PDF (no text layer) is no longer rejected outright: its
    # image_only pages were already rendered into `ingested.images` above,
    # and get sent to the LLM as images if the configured provider supports
    # vision. Whether it does is checked once, correctly, in
    # llm.client.extract() -- not here -- because that check has to account
    # for a per-group provider override (TOR_GROUP_<NAME>), which this
    # request-level code has no visibility into. If unsupported, extract()
    # raises ProviderUnsupportedError, already handled below as a 502.
    document_text = ingested.document_text

    groups = apply_group_overrides(FIELD_GROUPS, config.group_overrides)

    def _provider_for(name: str, override_model: str):
        # The one configured base_url is meant for whichever provider actually
        # needs it: either the document default itself, or an openai_compat
        # override naming a different provider than the default -- openai_compat
        # is the only provider that hard-requires a base_url to construct at
        # all, so withholding it there (just because the override's name
        # differs from the document default) would make that override
        # combination permanently fail.
        base_url = config.provider_base_url if name in (config.provider, "openai_compat") else None
        return get_provider(name, api_key=api_key_for_provider(name), base_url=base_url, model=override_model)

    def _run_extraction():
        # Provider construction (including openai_compat's synchronous HTTP
        # capability probe) must happen inside the worker thread too -- built
        # as an argument to run_in_threadpool, it would run on the asyncio
        # event loop instead and block every other concurrent request.
        provider = get_provider(
            config.provider,
            api_key=config.api_key,
            base_url=config.provider_base_url,
            model=config.model,
        )
        return llm_extract(
            document_text=document_text,
            provider=provider,
            model=config.model,
            groups=groups,
            provider_for=_provider_for,
            document_kind=ingested.meta.document_kind,
            images=ingested.images,
        )

    try:
        # llm_extract is a blocking (sync) call chain -- offload to a worker
        # thread so the event loop stays responsive, and cap wall time so a
        # stuck request doesn't hang forever. Note: canceling wait_for does
        # NOT stop the underlying thread (Python can't force-kill a thread)
        # -- on timeout the thread keeps running server-side even though the
        # client already got a 504. Acceptable for v0.1's single-user local
        # use; a real cancellation path is future work, not built here.
        run = await asyncio.wait_for(
            run_in_threadpool(_run_extraction),
            timeout=config.extraction_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504, detail="การวิเคราะห์ใช้เวลานานเกินไป ลองใหม่อีกครั้ง"
        ) from None
    except ExtractionValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except ProviderAuthError:
        raise HTTPException(
            status_code=500, detail=f"API key ของ provider '{config.provider}' ไม่ถูกต้อง"
        ) from None
    except ProviderRateLimitError:
        raise HTTPException(
            status_code=429, detail="ถูกจำกัดอัตราการเรียก API ลองใหม่อีกสักครู่"
        ) from None
    except ProviderUnsupportedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except ProviderAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None

    return assemble_document(
        run.document,
        ingest_meta=ingested.meta,
        provider=run.provider,
        model=run.model,
        usage=run.usage,
        duration_ms=run.duration_ms,
        cost=run.cost,
        source_preview=ingested.preview,
    )
