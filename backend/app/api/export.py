"""POST /api/export/csv -- flatten a TORDocument (posted back by the
frontend, which already has it from /api/extract) into a long-format CSV:
one row per extracted fact, each traceable to its locator/quote/confidence.

No id, no server-side lookup -- stays consistent with /api/extract's
stateless design. JSON export needs no endpoint at all: the frontend
already holds the exact response body from /api/extract and can save it
directly.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schema import Source, Sourced, TORDocument

router = APIRouter()

# `locator_kind` + `locator` replace what used to be a single `page` column.
# Deliberately breaking: a page number is only one of several locator shapes
# now (a DOCX cites a paragraph or table cell, an XLSX cites sheet+cell), so a
# `page` column would be blank for those formats and quietly lose the citation.
_CSV_COLUMNS = [
    "section",
    "index",
    "field",
    "value",
    "locator_kind",
    "locator",
    "quote",
    "confidence",
    "reason",
]

_EMPTY_LOCATOR = ("", "")


def _format_locator(source: Source | None) -> tuple[str, str]:
    """(kind, human-readable locator). Kept as its own column pair so the CSV
    stays machine-filterable by kind while the text stays readable to a person
    checking the value against the original document.
    """
    if source is None:
        return _EMPTY_LOCATOR
    if source.kind == "text_page":
        return source.kind, f"หน้า {source.page}"
    if source.kind == "vision_page":
        # Marked explicitly: this was read off a page image, not extracted
        # text, so a human double-check carries more weight here.
        return source.kind, f"หน้า {source.page} (อ่านจากภาพสแกน)"
    if source.kind == "paragraph":
        # ref is "para:12"
        return source.kind, f"ย่อหน้าที่ {source.ref.split(':', 1)[1]}"
    if source.kind == "table_cell_docx":
        # ref is "t1:r3:c2"
        t, r, c = (part[1:] for part in source.ref.split(":"))
        return source.kind, f"ตารางที่ {t} แถว {r} คอลัมน์ {c}"
    if source.kind == "cell_xlsx":
        # ref is already A1 notation ("Sheet1!B5") -- readable as-is
        return source.kind, source.ref
    return source.kind, source.ref or ""


def _row(section: str, field: str, sourced: Sourced, index: int | str = "") -> dict:
    locator_kind, locator = _format_locator(sourced.source)
    return {
        "section": section,
        "index": index,
        "field": field,
        "value": "" if sourced.value is None else sourced.value,
        "locator_kind": locator_kind,
        "locator": locator,
        "quote": "" if sourced.source is None else sourced.source.quote,
        "confidence": sourced.confidence,
        "reason": sourced.reason or "",
    }


def flatten_to_rows(doc: TORDocument) -> list[dict]:
    rows: list[dict] = []

    for field, sourced in (
        ("project_name", doc.project_name),
        ("project_id", doc.project_id),
        ("agency", doc.agency),
        ("announcement_date", doc.announcement_date),
        ("procurement_method", doc.procurement_method),
        ("budget_amount", doc.budget_amount),
        ("median_price", doc.median_price),
    ):
        rows.append(_row("basic_info", field, sourced))

    for i, kd in enumerate(doc.key_dates):
        for field in ("type", "date_be", "time", "location"):
            rows.append(_row("key_dates", field, getattr(kd, field), index=i))
        rows.append(
            {
                "section": "key_dates",
                "index": i,
                "field": "date_ce",
                "value": kd.date_ce,
                "locator_kind": "",
                "locator": "",
                "quote": "",
                "confidence": "",
                "reason": "",
            }
        )

    for bond_name, bond, percent in (
        ("bid_bond", doc.bid_bond, doc.bid_bond_percent_of_budget),
        ("contract_bond", doc.contract_bond, doc.contract_bond_percent_of_budget),
        ("warranty_bond", doc.warranty_bond, doc.warranty_bond_percent_of_budget),
    ):
        rows.append(_row(bond_name, "amount", bond.amount))
        rows.append(_row(bond_name, "percent_stated", bond.percent_stated))
        rows.append(_row(bond_name, "accepted_forms", bond.accepted_forms))
        rows.append(
            {
                "section": bond_name,
                "index": "",
                "field": "percent_of_budget_calculated",
                "value": percent if percent is not None else "",
                "locator_kind": "",
                "locator": "",
                "quote": "",
                "confidence": "",
                "reason": "" if percent is not None else "คำนวณไม่ได้ (ไม่มี amount หรือ budget_amount)",
            }
        )

    for i, q in enumerate(doc.qualifications):
        for field in ("text", "category", "operator", "value", "unit"):
            rows.append(_row("qualifications", field, getattr(q, field), index=i))

    for i, d in enumerate(doc.deliverables):
        for field in ("phase", "description", "days_from_signing", "payment_percent"):
            rows.append(_row("deliverables", field, getattr(d, field), index=i))

    rows.append(_row("penalty", "rate_percent_per_day", doc.penalty.rate_percent_per_day))
    rows.append(_row("penalty", "cap_percent", doc.penalty.cap_percent))

    for i, rd in enumerate(doc.required_documents):
        rows.append(_row("required_documents", "document", rd, index=i))

    ec = doc.evaluation_criteria
    rows.append(_row("evaluation_criteria", "method", ec.method))
    rows.append(_row("evaluation_criteria", "price_weight", ec.price_weight))
    rows.append(_row("evaluation_criteria", "technical_weight", ec.technical_weight))
    rows.append(_row("evaluation_criteria", "sub_criteria", ec.sub_criteria))

    for i, flag in enumerate(doc.risk_flags):
        flag_kind, flag_locator = _format_locator(flag.source)
        rows.append(
            {
                "section": "risk_flags",
                "index": i,
                "field": flag.origin,
                "value": flag.text,
                "locator_kind": flag_kind,
                "locator": flag_locator,
                "quote": flag.source.quote if flag.source else "",
                "confidence": "",
                "reason": "",
            }
        )

    c = doc.contact
    rows.append(_row("contact", "name_redacted", c.name_redacted))
    rows.append(_row("contact", "department", c.department))
    rows.append(_row("contact", "phone", c.phone))
    rows.append(_row("contact", "email", c.email))

    return rows


@router.post("/api/export/csv")
async def export_csv(doc: TORDocument) -> StreamingResponse:
    rows = flatten_to_rows(doc)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tor_analysis.csv"},
    )
