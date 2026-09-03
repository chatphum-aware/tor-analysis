from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from tests.unit.test_calculations import _minimal_extracted
from app.derive.calculations import assemble_document
from app.derive.pricing import Usage
from app.ingest.pdf_ingest import ingest_meta_from_scan_report
from app.pdf.scanned import DocumentScanReport, PageReport

client = TestClient(app)

_SCANNED_SAMPLE = Path.home() / "Downloads" / "29_44_Attach_TOR_1.pdf"


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_extract_without_api_key_returns_500(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = client.post(
        "/api/extract", files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")}
    )
    assert resp.status_code == 500
    assert "anthropic" in resp.json()["detail"]


def test_extract_empty_file_returns_400(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    resp = client.post("/api/extract", files={"file": ("test.pdf", b"", "application/pdf")})
    assert resp.status_code == 400


def test_extract_oversized_file_returns_413(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    too_big = b"0" * (2 * 1024 * 1024)
    resp = client.post(
        "/api/extract", files={"file": ("test.pdf", too_big, "application/pdf")}
    )
    assert resp.status_code == 413


def test_extract_unrecognized_format_returns_415(monkeypatch):
    """Bytes matching no known magic number are a format problem (415), not a
    corrupt-PDF problem (400) -- the filename claiming ".pdf" is not evidence,
    since dispatch is by magic bytes (see app/ingest/detect.py)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    resp = client.post(
        "/api/extract", files={"file": ("test.pdf", b"this is not a pdf", "application/pdf")}
    )
    assert resp.status_code == 415
    assert "PDF" in resp.json()["detail"]


def test_extract_corrupt_but_pdf_shaped_file_returns_400(monkeypatch):
    """Has the %PDF magic, so it dispatches to the PDF ingestor and fails
    there -- that IS a 400, and must not be swallowed by the 415 path."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    resp = client.post(
        "/api/extract",
        files={"file": ("test.pdf", b"%PDF-1.7\ntruncated garbage", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_extract_xlsx_returns_415_while_gated_off(monkeypatch):
    """XLSX ingestion exists but is disabled (no real Thai gov TOR found in
    .xlsx -- see app/ingest/dispatch.py). It must say which format it
    recognized rather than claiming the file is unreadable."""
    import io
    import zipfile

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    monkeypatch.delenv("TOR_ENABLE_XLSX", raising=False)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
    resp = client.post(
        "/api/extract",
        files={"file": ("t.xlsx", buf.getvalue(), "application/octet-stream")},
    )
    assert resp.status_code == 415
    assert "XLSX" in resp.json()["detail"]


def test_extract_docx_is_accepted_and_reaches_extraction(monkeypatch):
    """DOCX is supported (real Thai gov TORs circulate in this format), so a
    valid one must get past format dispatch. The fake key then fails the LLM
    call with a 500 -- which is proof it reached extraction rather than being
    rejected as a bad format."""
    import io

    from docx import Document

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    doc = Document()
    doc.add_paragraph("1. ความเป็นมา")
    buf = io.BytesIO()
    doc.save(buf)
    resp = client.post(
        "/api/extract",
        files={"file": ("tor.docx", buf.getvalue(), "application/octet-stream")},
    )
    assert resp.status_code not in (400, 415), resp.json()
    assert resp.status_code == 500  # fake key rejected downstream


def test_extract_scanned_file_now_reaches_extraction_via_vision(monkeypatch):
    """Phase 5 (vision OCR) means a scanned PDF is no longer rejected outright
    -- its image_only pages are rendered and sent to the LLM as images, and
    the configured provider (anthropic) supports that. A fake key still
    fails, but downstream at the LLM call (500), which is the proof this
    reached extraction instead of being blanket-rejected the way it was
    before this phase. See test_ingest.py for the ingestion-layer tests of
    the actual image rendering."""
    if not _SCANNED_SAMPLE.exists():
        import pytest

        pytest.skip(f"sample file not present: {_SCANNED_SAMPLE}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-that-would-401-if-called")
    with open(_SCANNED_SAMPLE, "rb") as f:
        resp = client.post(
            "/api/extract", files={"file": (_SCANNED_SAMPLE.name, f.read(), "application/pdf")}
        )
    assert resp.status_code == 500, resp.json()
    assert "API key" in resp.json()["detail"]


def test_extract_too_many_scanned_pages_returns_422(monkeypatch):
    """A document with more image_only pages than the vision cap must fail
    loudly (422) rather than silently sending only some of them -- a dropped
    page would look like its content was simply absent."""
    if not _SCANNED_SAMPLE.exists():
        import pytest

        pytest.skip(f"sample file not present: {_SCANNED_SAMPLE}")
    import app.ingest.pdf_ingest as pdf_ingest_module

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    monkeypatch.setattr(pdf_ingest_module, "MAX_VISION_PAGES", 1)
    with open(_SCANNED_SAMPLE, "rb") as f:
        resp = client.post(
            "/api/extract", files={"file": (_SCANNED_SAMPLE.name, f.read(), "application/pdf")}
        )
    assert resp.status_code == 422
    assert "หน้า" in resp.json()["detail"]


def test_export_csv_returns_csv_content_type():
    extracted = _minimal_extracted()
    scan_report = DocumentScanReport(
        page_count=1,
        pages=[PageReport(page_number=1, status="text", text_char_count=10, image_coverage_ratio=0.0)],
    )
    doc = assemble_document(
        extracted,
        ingest_meta=ingest_meta_from_scan_report(scan_report),
        provider="anthropic",
        model="claude-haiku-4-5",
        usage=Usage(input_tokens=1, output_tokens=1),
        duration_ms=1,
    )
    resp = client.post("/api/export/csv", json=doc.model_dump(mode="json"))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "project_name" in resp.text


def test_extraction_usage_json_keys_are_provider_neutral():
    """These key names are the public API contract and are mirrored by hand in
    frontend/src/types/schema.ts (there is no codegen). Anthropic's own field
    names must not leak into a provider-neutral response."""
    from app.models.schema import ExtractionUsage

    keys = set(ExtractionUsage(
        input_tokens=1, output_tokens=2, cache_write_tokens=3, cached_read_tokens=4
    ).model_dump().keys())
    assert keys == {"input_tokens", "output_tokens", "cache_write_tokens", "cached_read_tokens"}
