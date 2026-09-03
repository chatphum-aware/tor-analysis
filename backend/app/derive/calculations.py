"""Everything the LLM is forbidden from doing (rule #1): BE->CE date
conversion, bond percentages, and cross-checking a numeral amount against
its Thai spelled-out form. Assembles the final TORDocument from the raw
TORDocumentExtracted the model returned.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.derive.pricing import Cost, Usage, compute_cost
from app.models.schema import (
    BondInfo,
    ExtractionCost,
    ExtractionMeta,
    ExtractionUsage,
    KeyDate,
    KeyDateExtracted,
    RiskFlag,
    Sourced,
    TORDocument,
    TORDocumentExtracted,
)
from app.pdf.scanned import DocumentScanReport
from app.thai.normalize import be_to_ce
from app.thai.numbers import thai_number_words_to_int

_BE_YEAR_RE = re.compile(r"(24|25|26)\d{2}")  # a 4-digit BE year, modern range
_AMOUNT_TOLERANCE = 1.0  # baht -- forgives cents/rounding noise in OCR'd/typed amounts

# Sentinel distinguishing "caller didn't pass a cost" (compute it here, as
# before) from "caller passed cost=None" (a mixed-provider run's real,
# already-computed answer of "genuinely unpriceable" -- see llm/client.py).
# A caller that only has a single (provider, model) string, like every
# existing call site before Task 9's fix, never has this problem: passing
# nothing preserves their exact prior behavior unchanged.
_UNSET_COST = object()


def convert_be_date_to_ce(date_be: str) -> str | None:
    """"2569-03-15" -> "2026-03-15". Falls back to a bare year-substitution
    if the string isn't the requested ISO shape, but never guesses a date
    it can't find a BE year in -- returns None instead.
    """
    match = _BE_YEAR_RE.search(date_be)
    if not match:
        return None
    be_year = int(match.group(0))
    ce_year = be_to_ce(be_year)
    return date_be[: match.start()] + str(ce_year) + date_be[match.end() :]


def _bond_percent(bond: BondInfo, budget: Sourced[float]) -> float | None:
    if bond.amount.value is None or budget.value is None or budget.value == 0:
        return None
    return round(bond.amount.value / budget.value * 100, 4)


def _cross_check_amount(field_label: str, sourced: Sourced[float]) -> RiskFlag | None:
    """If the source quote also contains a Thai spelled-out amount, parse it
    and compare against the numeral value. Only ever ADDS a flag -- never
    silently picks one representation over the other (per the project's
    hard rule on this exact ambiguity).
    """
    if sourced.value is None or sourced.source is None:
        return None
    words_value = thai_number_words_to_int(sourced.source.quote)
    if words_value is None:
        return None  # quote has no spelled-out form to check against
    if abs(words_value - sourced.value) <= _AMOUNT_TOLERANCE:
        return None  # they agree
    return RiskFlag(
        text=(
            f"{field_label}: ตัวเลข ({sourced.value:,.2f}) กับจำนวนที่สะกดเป็นตัวอักษร "
            f"({words_value:,.2f}) ในข้อความเดียวกันไม่ตรงกัน — ต้องตรวจสอบกับต้นฉบับ"
        ),
        origin="derived",
        source=sourced.source,
    )


def _to_key_date(kd: KeyDateExtracted) -> KeyDate:
    date_ce = None
    if kd.date_be.value is not None:
        date_ce = convert_be_date_to_ce(kd.date_be.value)
    return KeyDate(
        type=kd.type,
        date_be=kd.date_be,
        time=kd.time,
        location=kd.location,
        date_ce=date_ce or "",
    )


def assemble_document(
    extracted: TORDocumentExtracted,
    *,
    scan_report: DocumentScanReport,
    provider: str,
    model: str,
    usage: Usage,
    duration_ms: int,
    extracted_at: datetime | None = None,
    cost: Cost | None = _UNSET_COST,  # type: ignore[assignment]
) -> TORDocument:
    derived_flags: list[RiskFlag] = []
    for label, field in (
        ("วงเงินงบประมาณ", extracted.budget_amount),
        ("ราคากลาง", extracted.median_price),
        ("หลักประกันการเสนอราคา", extracted.bid_bond.amount),
        ("หลักประกันสัญญา", extracted.contract_bond.amount),
        ("หลักประกันผลงาน", extracted.warranty_bond.amount),
    ):
        flag = _cross_check_amount(label, field)
        if flag:
            derived_flags.append(flag)

    if cost is _UNSET_COST:
        cost = compute_cost(provider, model, usage)
    if cost is None:
        # rule: never guess a price for a (provider, model) we don't have pricing for
        cost = Cost(
            usd=0.0,
            thb=0.0,
            usd_thb_rate=0.0,
            rate_source_date="",
            provider=provider,
            model=model,
            pricing_as_of="unknown",
            is_estimate=True,
        )

    return TORDocument(
        project_name=extracted.project_name,
        project_id=extracted.project_id,
        agency=extracted.agency,
        announcement_date=extracted.announcement_date,
        procurement_method=extracted.procurement_method,
        budget_amount=extracted.budget_amount,
        median_price=extracted.median_price,
        key_dates=[_to_key_date(kd) for kd in extracted.key_dates],
        bid_bond=extracted.bid_bond,
        bid_bond_percent_of_budget=_bond_percent(extracted.bid_bond, extracted.budget_amount),
        contract_bond=extracted.contract_bond,
        contract_bond_percent_of_budget=_bond_percent(extracted.contract_bond, extracted.budget_amount),
        warranty_bond=extracted.warranty_bond,
        warranty_bond_percent_of_budget=_bond_percent(extracted.warranty_bond, extracted.budget_amount),
        qualifications=extracted.qualifications,
        deliverables=extracted.deliverables,
        penalty=extracted.penalty,
        required_documents=extracted.required_documents,
        evaluation_criteria=extracted.evaluation_criteria,
        risk_flags=[*extracted.risk_flags, *derived_flags],
        contact=extracted.contact,
        extraction_meta=ExtractionMeta(
            page_count=scan_report.page_count,
            usable_text_page_ratio=round(scan_report.usable_text_ratio, 4),
            image_only_pages=[p.page_number for p in scan_report.pages if p.status == "image_only"],
            provider=provider,
            model=model,
            pricing_as_of=cost.pricing_as_of,
            extracted_at=extracted_at or datetime.now(),
            duration_ms=duration_ms,
            usage=ExtractionUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cached_read_tokens=usage.cached_read_tokens,
            ),
            cost=ExtractionCost(
                usd=cost.usd,
                thb=cost.thb,
                usd_thb_rate=cost.usd_thb_rate,
                rate_source_date=cost.rate_source_date,
                is_estimate=cost.is_estimate,
            ),
        ),
    )
