from app.derive.calculations import (
    _bond_percent,
    _cross_check_amount,
    assemble_document,
    convert_be_date_to_ce,
)
from app.derive.pricing import Usage
from app.ingest.pdf_ingest import ingest_meta_from_scan_report
from app.models.schema import BondInfo, Source, Sourced, TORDocumentExtracted
from app.pdf.scanned import DocumentScanReport, PageReport


def s(value, page=1, quote="q", confidence="high"):
    return Sourced(value=value, source=Source(kind="text_page", page=page, quote=quote), confidence=confidence)


def null(reason="ไม่พบ", confidence="low"):
    return Sourced(value=None, confidence=confidence, reason=reason)


def test_be_to_ce_date_conversion():
    assert convert_be_date_to_ce("2569-03-15") == "2026-03-15"


def test_be_to_ce_no_year_found_returns_none():
    assert convert_be_date_to_ce("ไม่ระบุวันที่") is None


def test_bond_percent_computed_not_from_model():
    bond = BondInfo(amount=s(50_000.0), percent_stated=null(), accepted_forms=null())
    budget = s(1_000_000.0)
    assert _bond_percent(bond, budget) == 5.0


def test_bond_percent_none_when_budget_missing():
    bond = BondInfo(amount=s(50_000.0), percent_stated=null(), accepted_forms=null())
    assert _bond_percent(bond, null()) is None


def test_cross_check_flags_mismatch():
    field = s(
        1_600_000.0,
        quote="จำนวนเงิน 1,600,000.00 บาท (หนึ่งล้านห้าแสนบาทถ้วน)",
    )
    flag = _cross_check_amount("วงเงินงบประมาณ", field)
    assert flag is not None
    assert flag.origin == "derived"
    assert "1,600,000.00" in flag.text or "1,600,000" in flag.text


def test_cross_check_silent_when_matching():
    field = s(
        1_500_000.0,
        quote="จำนวนเงิน 1,500,000.00 บาท (หนึ่งล้านห้าแสนบาทถ้วน)",
    )
    assert _cross_check_amount("วงเงินงบประมาณ", field) is None


def test_cross_check_silent_when_no_word_form_present():
    field = s(1_500_000.0, quote="จำนวนเงิน 1,500,000.00 บาท")
    assert _cross_check_amount("วงเงินงบประมาณ", field) is None


def _minimal_extracted() -> TORDocumentExtracted:
    return TORDocumentExtracted.model_validate(
        {
            "project_name": s("โครงการทดสอบ").model_dump(),
            "project_id": s("TOR-001").model_dump(),
            "agency": s("กรมทดสอบ").model_dump(),
            "announcement_date": s("2569-01-01").model_dump(),
            "procurement_method": s("e-bidding").model_dump(),
            "budget_amount": s(1_000_000.0).model_dump(),
            "median_price": null().model_dump(),
            "key_dates": [
                {
                    "type": s("ยื่นข้อเสนอ").model_dump(),
                    "date_be": s("2569-03-15").model_dump(),
                    "time": s("10:00").model_dump(),
                    "location": s("ห้องประชุม").model_dump(),
                }
            ],
            "bid_bond": {
                "amount": s(50_000.0).model_dump(),
                "percent_stated": null().model_dump(),
                "accepted_forms": null().model_dump(),
            },
            "contract_bond": {
                "amount": null().model_dump(),
                "percent_stated": null().model_dump(),
                "accepted_forms": null().model_dump(),
            },
            "warranty_bond": {
                "amount": null().model_dump(),
                "percent_stated": null().model_dump(),
                "accepted_forms": null().model_dump(),
            },
            "qualifications": [],
            "deliverables": [],
            "penalty": {"rate_percent_per_day": null().model_dump(), "cap_percent": null().model_dump()},
            "required_documents": [],
            "evaluation_criteria": {
                "method": null().model_dump(),
                "price_weight": null().model_dump(),
                "technical_weight": null().model_dump(),
                "sub_criteria": null().model_dump(),
            },
            "risk_flags": [],
            "contact": {
                "name_redacted": null().model_dump(),
                "department": null().model_dump(),
                "phone": null().model_dump(),
                "email": null().model_dump(),
            },
        }
    )


def test_assemble_document_end_to_end():
    extracted = _minimal_extracted()
    scan_report = DocumentScanReport(
        page_count=5,
        pages=[
            PageReport(page_number=1, status="text", text_char_count=500, image_coverage_ratio=0.0),
            PageReport(page_number=2, status="image_only", text_char_count=0, image_coverage_ratio=0.9),
        ],
    )
    usage = Usage(input_tokens=1000, output_tokens=200, cache_write_tokens=1000, cached_read_tokens=0)

    doc = assemble_document(
        extracted,
        ingest_meta=ingest_meta_from_scan_report(scan_report),
        provider="anthropic",
        model="claude-haiku-4-5",
        usage=usage,
        duration_ms=1234,
    )

    assert doc.key_dates[0].date_ce == "2026-03-15"
    assert doc.bid_bond_percent_of_budget == 5.0
    assert doc.contract_bond_percent_of_budget is None
    assert doc.extraction_meta.page_count == 5
    assert doc.extraction_meta.image_only_pages == [2]
    assert doc.extraction_meta.cost.usd > 0
    assert doc.extraction_meta.model == "claude-haiku-4-5"
