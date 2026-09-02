import pytest
from pydantic import ValidationError

from app.models.schema import Source, Sourced, TORDocumentExtracted


def test_sourced_value_requires_source():
    with pytest.raises(ValidationError, match="source is missing"):
        Sourced[str](value="งบซื้อคอมพิวเตอร์", confidence="high")


def test_sourced_null_requires_reason():
    with pytest.raises(ValidationError, match="no reason given"):
        Sourced[str](value=None, confidence="low")


def test_sourced_null_with_reason_is_valid():
    s = Sourced[str](value=None, confidence="low", reason="ไม่พบชื่อโครงการในเอกสาร")
    assert s.value is None
    assert s.reason


def test_sourced_value_with_source_is_valid():
    s = Sourced[str](
        value="โครงการปรับปรุงห้องประชุม",
        source=Source(page=1, quote="ชื่อโครงการ: โครงการปรับปรุงห้องประชุม"),
        confidence="high",
    )
    assert s.value == "โครงการปรับปรุงห้องประชุม"


def test_json_schema_generation_does_not_error():
    # this is what messages.parse(output_format=TORDocumentExtracted) relies on
    schema = TORDocumentExtracted.model_json_schema()
    assert schema["type"] == "object"
    assert "project_name" in schema["properties"]
    assert "key_dates" in schema["properties"]


def test_minimal_valid_document_round_trips():
    def s(value, page=1, quote="q", confidence="high"):
        return {"value": value, "source": {"page": page, "quote": quote}, "confidence": confidence}

    def null(reason="ไม่พบ", confidence="low"):
        return {"value": None, "confidence": confidence, "reason": reason}

    doc = TORDocumentExtracted.model_validate(
        {
            "project_name": s("โครงการทดสอบ"),
            "project_id": s("TOR-001"),
            "agency": s("กรมทดสอบ"),
            "announcement_date": s("1 มกราคม 2569"),
            "procurement_method": s("e-bidding"),
            "budget_amount": null(),
            "median_price": null(),
            "key_dates": [],
            "bid_bond": {
                "amount": null(),
                "percent_stated": null(),
                "accepted_forms": null(),
            },
            "contract_bond": {
                "amount": null(),
                "percent_stated": null(),
                "accepted_forms": null(),
            },
            "warranty_bond": {
                "amount": null(),
                "percent_stated": null(),
                "accepted_forms": null(),
            },
            "qualifications": [],
            "deliverables": [],
            "penalty": {"rate_percent_per_day": null(), "cap_percent": null()},
            "required_documents": [],
            "evaluation_criteria": {
                "method": null(),
                "price_weight": null(),
                "technical_weight": null(),
                "sub_criteria": null(),
            },
            "risk_flags": [],
            "contact": {
                "name_redacted": null(),
                "department": null(),
                "phone": null(),
                "email": null(),
            },
        }
    )
    assert doc.project_name.value == "โครงการทดสอบ"
    assert doc.budget_amount.value is None
    assert doc.budget_amount.reason
