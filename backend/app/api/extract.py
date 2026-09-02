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
from app.llm.client import ExtractionValidationError, extract as llm_extract
from app.llm.groups import FIELD_GROUPS, apply_group_overrides
from app.llm.providers.base import ProviderAPIError, ProviderAuthError, ProviderRateLimitError
from app.llm.providers.registry import get_provider
from app.models.schema import TORDocument
from app.pdf.extract import build_document_text, extract_document_from_bytes

router = APIRouter()


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

    try:
        result = extract_document_from_bytes(data)
    except Exception as exc:  # noqa: BLE001 - any PyMuPDF open/parse failure -> 400
        raise HTTPException(status_code=400, detail=f"เปิดไฟล์ PDF ไม่ได้: {exc}") from None

    report = result.scan_report
    if report.usable_text_ratio == 0.0:
        # rule: never return an empty result for a scanned file -- say so explicitly
        raise HTTPException(
            status_code=422,
            detail=(
                "เอกสารนี้เป็นไฟล์สแกน ไม่มีข้อความให้ดึงเลยแม้แต่หน้าเดียว — "
                "ยังไม่รองรับไฟล์สแกนใน v0.1 (ไม่มี OCR)"
            ),
        )

    document_text = build_document_text(result.blocks)

    groups = apply_group_overrides(FIELD_GROUPS, config.group_overrides)

    def _provider_for(name: str, override_model: str):
        # An override's base_url only applies when it names the SAME
        # provider as the document default (e.g. a local openai_compat
        # endpoint overriding one group's model); a different provider
        # gets its own key but no base_url override.
        base_url = config.provider_base_url if name == config.provider else None
        return get_provider(name, api_key=api_key_for_provider(name), base_url=base_url, model=override_model)

    try:
        # llm_extract is a blocking (sync) call chain -- offload to a worker
        # thread so the event loop stays responsive, and cap wall time so a
        # stuck request doesn't hang forever. Note: canceling wait_for does
        # NOT stop the underlying thread (Python can't force-kill a thread)
        # -- on timeout the thread keeps running server-side even though the
        # client already got a 504. Acceptable for v0.1's single-user local
        # use; a real cancellation path is future work, not built here.
        run = await asyncio.wait_for(
            run_in_threadpool(
                llm_extract,
                document_text=document_text,
                provider=get_provider(
                    config.provider,
                    api_key=config.api_key,
                    base_url=config.provider_base_url,
                    model=config.model,
                ),
                model=config.model,
                groups=groups,
                provider_for=_provider_for,
            ),
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
    except ProviderAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None

    return assemble_document(
        run.document,
        scan_report=report,
        provider=config.provider,
        model=run.model,
        usage=run.usage,
        duration_ms=run.duration_ms,
    )
