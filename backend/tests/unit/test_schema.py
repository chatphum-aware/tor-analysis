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
        source=Source(kind="text_page", page=1, quote="ชื่อโครงการ: โครงการปรับปรุงห้องประชุม"),
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
        return {
            "value": value,
            "source": {"kind": "text_page", "page": page, "quote": quote},
            "confidence": confidence,
        }

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


# --- Source locator shape (rule #2's locator, generalized beyond PDF pages) ---
#
# `Source` locates a fact either by `page` (PDF) or by a `ref` string
# (DOCX/XLSX, which have no page numbers). These tests pin the validator that
# enforces which field goes with which `kind`, AND `ref`'s format -- the model
# writes that string, and an unparseable one would be a citation nobody could
# go check, which defeats rule #2 entirely.
#
# The locators were deliberately collapsed into one `ref` string rather than
# typed per-format fields: eight typed fields pushed the `misc` group past
# Anthropic's grammar compiler (confirmed live, 2026-09-03).


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "text_page", "page": 3},
        {"kind": "vision_page", "page": 3},
        {"kind": "paragraph", "ref": "para:12"},
        {"kind": "table_cell_docx", "ref": "t1:r3:c2"},
        {"kind": "cell_xlsx", "ref": "Sheet1!B5"},
        pytest.param(
            {"kind": "cell_xlsx", "ref": "งบประมาณ 2569!AA10"},
            id="xlsx_thai_sheet_name_and_two_letter_column",
        ),
    ],
)
def test_source_accepts_locator_matching_its_kind(kwargs):
    assert Source(quote="q", **kwargs).kind == kwargs["kind"]


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"kind": "text_page"}, id="page_kind_without_a_page"),
        pytest.param({"kind": "paragraph"}, id="ref_kind_without_a_ref"),
        pytest.param({"kind": "cell_xlsx"}, id="xlsx_without_a_ref"),
    ],
)
def test_source_rejects_missing_required_locator(kwargs):
    with pytest.raises(ValidationError):
        Source(quote="q", **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"kind": "text_page", "page": 1, "ref": "para:2"}, id="page_kind_with_a_ref"),
        pytest.param({"kind": "cell_xlsx", "ref": "Sheet1!B5", "page": 3}, id="ref_kind_with_a_page"),
    ],
)
def test_source_rejects_locator_from_another_format(kwargs):
    with pytest.raises(ValidationError):
        Source(quote="q", **kwargs)


@pytest.mark.parametrize(
    "ref",
    [
        pytest.param("ตารางที่สอง", id="prose_instead_of_a_locator"),
        pytest.param("para:twelve", id="paragraph_index_not_a_number"),
        pytest.param("12", id="bare_number_without_the_para_prefix"),
    ],
)
def test_source_rejects_unparseable_paragraph_ref(ref):
    with pytest.raises(ValidationError):
        Source(kind="paragraph", quote="q", ref=ref)


@pytest.mark.parametrize(
    "kind,ref",
    [
        pytest.param("table_cell_docx", "t1:r3", id="table_ref_missing_column"),
        pytest.param("table_cell_docx", "1:3:2", id="table_ref_missing_prefixes"),
        pytest.param("cell_xlsx", "B5", id="xlsx_ref_missing_sheet"),
        pytest.param("cell_xlsx", "Sheet1!5B", id="xlsx_ref_reversed_a1_notation"),
    ],
)
def test_source_rejects_malformed_ref_for_its_kind(kind, ref):
    with pytest.raises(ValidationError):
        Source(kind=kind, quote="q", ref=ref)
