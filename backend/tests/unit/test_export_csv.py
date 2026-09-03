from app.api.export import flatten_to_rows
from app.derive.calculations import assemble_document
from app.derive.pricing import Usage
from app.ingest.pdf_ingest import ingest_meta_from_scan_report
from app.models.schema import Source, Sourced
from app.pdf.scanned import DocumentScanReport, PageReport
from tests.unit.test_calculations import _minimal_extracted


def _build_doc():
    extracted = _minimal_extracted()
    scan_report = DocumentScanReport(
        page_count=1,
        pages=[PageReport(page_number=1, status="text", text_char_count=100, image_coverage_ratio=0.0)],
    )
    return assemble_document(
        extracted,
        ingest_meta=ingest_meta_from_scan_report(scan_report),
        provider="anthropic",
        model="claude-haiku-4-5",
        usage=Usage(input_tokens=10, output_tokens=10),
        duration_ms=1,
    )


def test_flatten_includes_basic_info_rows():
    doc = _build_doc()
    rows = flatten_to_rows(doc)
    project_name_rows = [r for r in rows if r["section"] == "basic_info" and r["field"] == "project_name"]
    assert len(project_name_rows) == 1
    assert project_name_rows[0]["value"] == "โครงการทดสอบ"


def test_flatten_key_dates_includes_derived_date_ce():
    doc = _build_doc()
    rows = flatten_to_rows(doc)
    ce_rows = [r for r in rows if r["section"] == "key_dates" and r["field"] == "date_ce"]
    assert len(ce_rows) == 1
    assert ce_rows[0]["value"] == "2026-03-15"


def test_flatten_bond_percent_of_budget_is_calculated_field():
    doc = _build_doc()
    rows = flatten_to_rows(doc)
    pct_rows = [r for r in rows if r["section"] == "bid_bond" and r["field"] == "percent_of_budget_calculated"]
    assert len(pct_rows) == 1
    assert pct_rows[0]["value"] == 5.0  # 50,000 / 1,000,000 * 100, from test_calculations fixture


def test_flatten_null_field_has_empty_value_and_a_reason():
    doc = _build_doc()
    rows = flatten_to_rows(doc)
    median_rows = [r for r in rows if r["section"] == "basic_info" and r["field"] == "median_price"]
    assert len(median_rows) == 1
    assert median_rows[0]["value"] == ""
    assert median_rows[0]["reason"]


def test_flatten_all_rows_have_every_column():
    doc = _build_doc()
    rows = flatten_to_rows(doc)
    expected_cols = {
        "section",
        "index",
        "field",
        "value",
        "locator_kind",
        "locator",
        "quote",
        "confidence",
        "reason",
    }
    for row in rows:
        assert set(row.keys()) == expected_cols
