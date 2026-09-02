from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from tests.unit.test_calculations import _minimal_extracted
from app.derive.calculations import assemble_document
from app.derive.pricing import Usage
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
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


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


def test_extract_invalid_pdf_returns_400(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
    resp = client.post(
        "/api/extract", files={"file": ("test.pdf", b"this is not a pdf", "application/pdf")}
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_extract_scanned_file_returns_422_without_calling_api(monkeypatch):
    if not _SCANNED_SAMPLE.exists():
        import pytest

        pytest.skip(f"sample file not present: {_SCANNED_SAMPLE}")
    # a fake key that would fail against the real API -- proves the scan
    # gate rejects BEFORE any network call happens (no AuthenticationError
    # bubbles up; it must be the 422 scan message, not a 500 from a bad key)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-that-would-401-if-called")
    with open(_SCANNED_SAMPLE, "rb") as f:
        resp = client.post(
            "/api/extract", files={"file": (_SCANNED_SAMPLE.name, f.read(), "application/pdf")}
        )
    assert resp.status_code == 422
    assert "สแกน" in resp.json()["detail"]


def test_export_csv_returns_csv_content_type():
    extracted = _minimal_extracted()
    scan_report = DocumentScanReport(
        page_count=1,
        pages=[PageReport(page_number=1, status="text", text_char_count=10, image_coverage_ratio=0.0)],
    )
    doc = assemble_document(
        extracted,
        scan_report=scan_report,
        model="claude-haiku-4-5",
        usage=Usage(input_tokens=1, output_tokens=1),
        duration_ms=1,
    )
    resp = client.post("/api/export/csv", json=doc.model_dump(mode="json"))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "project_name" in resp.text
