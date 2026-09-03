"""Pydantic schema -- the source of truth used by the extraction call, the
API response, and the eval scorer (see the plan's Impact/Risk Check: this
file is shared by all three, and changing it invalidates existing
tests/expected/*.json fixtures).

Two layers, matching the project's hard rule #1 ("LLM must never compute
anything"):

  - `TORDocumentExtracted` is what we ask Claude to fill in via
    `messages.parse(output_format=...)`. Every leaf value is wrapped in
    `Sourced[T]`: a value, its `source` (locator + quote), a `confidence`, and
    -- if the value is null -- a `reason`. Nothing in this layer is
    computed; it is either found on a page or it's null with a reason.

  - `TORDocument` (defined at the bottom) is the full API/export shape:
    the extracted layer plus fields Python derives afterward (date_ce from
    date_be, bond percentages from amount/budget, cross-check risk_flags,
    extraction_meta). Built in Step 3's derive/calculations.py.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar("T")

Confidence = Literal["high", "medium", "low"]

ProcurementMethod = Literal["e-bidding", "คัดเลือก", "เฉพาะเจาะจง"]

KeyDateType = Literal[
    "ขอรับเอกสาร",
    "ชี้แจงรายละเอียด",
    "ยื่นข้อเสนอ",
    "เสนอราคา",
    "ประกาศผล",
]

QualificationCategory = Literal[
    "ทุนจดทะเบียน",
    "ผลงานที่ผ่านมา",
    "ใบอนุญาต",
    "บุคลากร",
    "เครื่องจักร",
    "มาตรฐาน",
    "อื่น ๆ",
]

QualificationOperator = Literal["ไม่น้อยกว่า", "ไม่เกิน", "เท่ากับ", "อย่างน้อย"]

# Which input format a document came from. Lives here rather than in
# app/ingest/ because it ships in the API response; app.ingest.base imports it
# from this module, keeping the dependency pointing one way only.
DocumentKind = Literal["pdf", "docx", "xlsx"]


SourceKind = Literal["text_page", "vision_page", "paragraph", "table_cell_docx", "cell_xlsx"]

# Non-page locators collapse into ONE string field rather than getting a typed
# field each. This is not a stylistic choice: eight typed locator fields pushed
# the `misc` group past Anthropic's grammar compiler ("Schema is too complex for
# compilation", confirmed live on claude-haiku-4-5, 2026-09-03), because `Source`
# is referenced at all ~26 Sourced leaves. Collapsing to page+ref puts the group
# back at ~3.6KB, next to the 3.8KB shape that compiles today. The alternative --
# a 7th FieldGroup -- would resend the whole document text once more on every
# single extraction, a permanent cost increase, to buy typed coordinates we only
# ever need for display and one highlight lookup.
_REF_FORMATS: dict[str, tuple[str, str]] = {
    # kind: (regex the `ref` string must match, human example)
    "paragraph": (r"^para:\d+$", "para:12"),
    "table_cell_docx": (r"^t\d+:r\d+:c\d+$", "t1:r3:c2"),
    "cell_xlsx": (r"^.+![A-Z]+\d+$", "Sheet1!B5"),
}
_PAGE_KINDS: tuple[str, ...] = ("text_page", "vision_page")


# NOTE: keep Source's docstring SHORT and put the reasoning in comments like
# this one. Pydantic ships a model's docstring into its JSON schema as
# `description`, and Source is referenced at all ~26 Sourced leaves -- a
# 1.4KB docstring here cost ~1.4KB in EVERY field group's schema and helped
# push `misc` past Anthropic's grammar compiler. Comments cost nothing.
#
# Rule #2 requires a locator plus a verbatim quote. The locator's shape
# depends on the document's format, because "page" is a PDF concept that DOCX
# and XLSX genuinely do not have -- a Word page break is a rendering artifact
# of the reader's page size, not a stored fact, and a spreadsheet's
# addressable unit is a cell. `kind` says which field is meaningful:
#
#   - text_page        PDF with a real text layer      -> page
#   - vision_page      scanned PDF page read as image  -> page
#   - paragraph        DOCX body paragraph             -> ref "para:12"
#   - table_cell_docx  DOCX table cell                 -> ref "t1:r3:c2"
#   - cell_xlsx        XLSX cell                       -> ref "Sheet1!B5"
#
# vision_page stays distinct from text_page on purpose: its `quote` is the
# model's transcription of an image, not text extracted byte-for-byte, so it
# carries a different level of trust and must not be silently conflated.
#
# `ref`'s format is regex-checked per kind, and that check is load-bearing,
# not decoration: the model writes this string, and an unparseable one ("the
# second table") would be a citation no human or viewer could go check --
# which is the entire point of rule #2.
class Source(BaseModel):
    """Where a value came from: a locator (page or ref, per kind) + quote."""

    kind: SourceKind
    quote: str

    page: int | None = None
    ref: str | None = None

    @model_validator(mode="after")
    def _enforce_kind_shape(self) -> "Source":
        if self.kind in _PAGE_KINDS:
            if self.page is None:
                raise ValueError(
                    f"source kind {self.kind!r} requires `page` but it was null "
                    f"-- rule #2 needs a locator that actually points somewhere"
                )
            if self.ref is not None:
                raise ValueError(
                    f"source kind {self.kind!r} locates by `page`, so `ref` must "
                    f"be null (got {self.ref!r})"
                )
            return self

        pattern, example = _REF_FORMATS[self.kind]
        if self.ref is None:
            raise ValueError(
                f"source kind {self.kind!r} requires `ref` (e.g. {example!r}) "
                f"but it was null -- rule #2 needs a locator that actually "
                f"points somewhere"
            )
        if self.page is not None:
            raise ValueError(
                f"source kind {self.kind!r} locates by `ref`, so `page` must be "
                f"null -- this document format has no page numbers "
                f"(got page={self.page!r})"
            )
        if not re.match(pattern, self.ref):
            raise ValueError(
                f"source kind {self.kind!r} needs `ref` shaped like {example!r} "
                f"so it can be resolved back to a place in the document; "
                f"got {self.ref!r}"
            )
        return self


class Sourced(BaseModel, Generic[T]):
    """A single extracted fact: value + where it came from + how sure the
    model is + (if null) why it couldn't be found.

    Rule #2: non-null value requires a source. Rule #3: null value
    requires a reason instead of a guess. Rule #4: confidence is always
    required, null or not.
    """

    value: T | None = None
    source: Source | None = None
    confidence: Confidence
    reason: str | None = None

    @model_validator(mode="after")
    def _enforce_traceability_rules(self) -> "Sourced[T]":
        if self.value is None and not self.reason:
            raise ValueError(
                "value is null but no reason given -- rule #3 forbids a blank "
                "null with no explanation"
            )
        if self.value is not None and self.source is None:
            raise ValueError(
                "value is present but source is missing -- rule #2 requires "
                "a locator+quote for every non-null field"
            )
        return self


class KeyDateExtracted(BaseModel):
    """Extraction-layer only. `date_ce` is NOT here -- it's derived in
    Python from `date_be` (rule #1: the model never computes ค.ศ. itself).
    """

    type: Sourced[KeyDateType]
    date_be: Sourced[str]  # raw Buddhist-Era date as found, e.g. "15 มีนาคม 2569"
    time: Sourced[str]
    location: Sourced[str]


class BondInfo(BaseModel):
    """Extraction-layer only. `percent_of_budget` is NOT here -- rule #1
    explicitly calls this out: code computes the percentage, not the model.
    `percent_stated` captures a percentage ONLY if the document states one
    explicitly in words (e.g. "ไม่น้อยกว่าร้อยละ 5"); it's a separate raw
    fact from `amount`, not a computation.
    """

    amount: Sourced[float]
    percent_stated: Sourced[float]
    accepted_forms: Sourced[list[str]]


class QualificationItem(BaseModel):
    text: Sourced[str]
    category: Sourced[QualificationCategory]
    operator: Sourced[QualificationOperator]
    value: Sourced[float]
    unit: Sourced[str]


class DeliverableItem(BaseModel):
    phase: Sourced[str]
    description: Sourced[str]
    days_from_signing: Sourced[int]
    payment_percent: Sourced[float]


class PenaltyInfo(BaseModel):
    rate_percent_per_day: Sourced[float]
    cap_percent: Sourced[float]


class EvaluationCriteria(BaseModel):
    method: Sourced[str]
    price_weight: Sourced[float]
    technical_weight: Sourced[float]
    sub_criteria: Sourced[list[str]]


class ContactInfo(BaseModel):
    # name_redacted: the model must generalize a personal name to a role/
    # title (e.g. "หัวหน้าฝ่ายพัสดุ") rather than quote it verbatim --
    # enforced by the extraction prompt, not by this schema.
    name_redacted: Sourced[str]
    department: Sourced[str]
    phone: Sourced[str]
    email: Sourced[str]


class RiskFlag(BaseModel):
    """Not a Sourced[T] -- a risk flag either exists in the list or it
    doesn't (no "null risk flag" concept). `origin` distinguishes flags the
    model noticed in the text (e.g. a brand-locked spec) from flags Python
    adds later by cross-checking two extracted values against each other
    (e.g. budget_amount vs. the spelled-out amount not matching).
    """

    text: str
    origin: Literal["model", "derived"]
    source: Source | None = None


class ExtractionUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int  # 0 on providers without prompt caching
    cached_read_tokens: int  # 0 on providers that don't report cache hits


class ExtractionCost(BaseModel):
    usd: float
    thb: float
    usd_thb_rate: float
    rate_source_date: str
    is_estimate: bool = True


class SheetCell(BaseModel):
    ref: str  # A1 notation within its sheet, e.g. "B5"
    value: str  # stringified cell value, exactly as ingested


class SheetPreview(BaseModel):
    name: str
    cells: list[SheetCell]
    # True when the sheet had more populated cells than the preview cap.
    # Surfaced rather than silently trimmed, so the UI can say the view is
    # partial instead of implying the citation isn't there.
    truncated: bool = False


class DocxBlock(BaseModel):
    ref: str  # "para:12" or "t1:r3:c2" -- matches Source.ref verbatim
    text: str
    kind: Literal["paragraph", "table_cell"]


class SourcePreview(BaseModel):
    """Enough of the source document for the frontend to render it and
    highlight a citation.

    PDFs don't need this -- the browser renders the user's own file via
    react-pdf. XLSX (and later DOCX) have no native browser renderer, and
    the backend has already parsed the file to build `document_text`, so it
    passes that structure along rather than making the frontend re-parse the
    upload with a second, heavier library.
    """

    document_kind: DocumentKind
    # Exactly one of these is populated, per document_kind: sheets for xlsx,
    # blocks (paragraphs and table cells, in document order) for docx.
    sheets: list[SheetPreview] = []
    blocks: list[DocxBlock] = []


class ExtractionMeta(BaseModel):
    """Metadata about the extraction run itself -- not document content, so
    it is intentionally excluded from eval scoring (see the plan's
    Impact/Risk Check: this field changes every run and must not be scored).
    """

    # Which format the upload actually was, decided by magic bytes (see
    # app/ingest/detect.py). The three page-shaped fields below are null for
    # formats that have no pages -- `document_kind` is what explains why, so
    # unlike rule #3's nulls they need no separate reason.
    document_kind: DocumentKind
    page_count: int | None  # pdf only
    usable_text_page_ratio: float | None  # pdf only, from scanned.DocumentScanReport
    image_only_pages: list[int] | None  # pdf only
    paragraph_count: int | None = None  # docx only
    sheet_names: list[str] | None = None  # xlsx only
    provider: str
    model: str
    pricing_as_of: str
    extracted_at: datetime
    duration_ms: int
    usage: ExtractionUsage
    cost: ExtractionCost


class TORDocumentExtracted(BaseModel):
    """The full extraction-layer shape (merged from all FieldGroup calls --
    see llm/groups.py). NOT sent to the API directly: real testing against
    Claude's structured-output grammar compiler showed this whole schema
    (~26 Sourced leaves across mixed nested types) fails with "schema too
    complex for compilation" / "compiled grammar is too large" (both
    observed, verbatim, from real 400 responses). Isolated probes confirmed
    a flat list of ~13 identical Sourced[str] fields compiles fine, and so
    does a single nested submodel repeated 3x -- the API's structured
    output has a real complexity ceiling well below this document's total
    size. Each of the 6 group schemas below stays comfortably inside the
    shapes that were empirically confirmed to compile.
    """

    project_name: Sourced[str]
    project_id: Sourced[str]
    agency: Sourced[str]
    announcement_date: Sourced[str]  # raw BE date text, same reasoning as KeyDateExtracted.date_be
    procurement_method: Sourced[ProcurementMethod]
    budget_amount: Sourced[float]
    median_price: Sourced[float]
    key_dates: list[KeyDateExtracted]
    bid_bond: BondInfo
    contract_bond: BondInfo
    warranty_bond: BondInfo
    qualifications: list[QualificationItem]
    deliverables: list[DeliverableItem]
    penalty: PenaltyInfo
    required_documents: list[Sourced[str]]
    evaluation_criteria: EvaluationCriteria
    risk_flags: list[RiskFlag]  # model-contributed only at this layer
    contact: ContactInfo


# ---------------------------------------------------------------------------
# Per-call group schemas. Each is sent to messages.stream(output_format=...)
# individually (see llm/client.py); results are merged into a
# TORDocumentExtracted afterward. See the module docstring above for why
# this split exists -- it's a real API constraint hit on the first live
# call, not a speculative optimization.
# ---------------------------------------------------------------------------


class BasicInfoGroup(BaseModel):
    project_name: Sourced[str]
    project_id: Sourced[str]
    agency: Sourced[str]
    announcement_date: Sourced[str]
    procurement_method: Sourced[ProcurementMethod]
    budget_amount: Sourced[float]
    median_price: Sourced[float]


class KeyDatesGroup(BaseModel):
    key_dates: list[KeyDateExtracted]


class BondsGroup(BaseModel):
    bid_bond: BondInfo
    contract_bond: BondInfo
    warranty_bond: BondInfo


class QualificationsGroup(BaseModel):
    qualifications: list[QualificationItem]


class DeliverablesGroup(BaseModel):
    deliverables: list[DeliverableItem]


class MiscGroup(BaseModel):
    penalty: PenaltyInfo
    required_documents: list[Sourced[str]]
    evaluation_criteria: EvaluationCriteria
    risk_flags: list[RiskFlag]
    contact: ContactInfo


class KeyDate(KeyDateExtracted):
    date_ce: str  # derived: be_to_ce() applied to date_be's year, in Step 3


class TORDocument(BaseModel):
    """Full API/export shape: extraction layer + Python-derived fields.
    Assembled by derive/calculations.py, never constructed by the model.
    """

    project_name: Sourced[str]
    project_id: Sourced[str]
    agency: Sourced[str]
    announcement_date: Sourced[str]
    procurement_method: Sourced[ProcurementMethod]
    budget_amount: Sourced[float]
    median_price: Sourced[float]
    key_dates: list[KeyDate]
    bid_bond: BondInfo
    bid_bond_percent_of_budget: float | None  # derived: amount / budget_amount
    contract_bond: BondInfo
    contract_bond_percent_of_budget: float | None
    warranty_bond: BondInfo
    warranty_bond_percent_of_budget: float | None
    qualifications: list[QualificationItem]
    deliverables: list[DeliverableItem]
    penalty: PenaltyInfo
    required_documents: list[Sourced[str]]
    evaluation_criteria: EvaluationCriteria
    risk_flags: list[RiskFlag]  # model flags + derived cross-check flags, merged
    contact: ContactInfo
    extraction_meta: ExtractionMeta
    # Only populated for formats the browser can't render itself (XLSX today).
    # Optional and last so PDF responses are byte-for-byte what they were, and
    # so the eval scorer -- which iterates the ground truth's keys, not the
    # response's -- never sees it.
    source_preview: SourcePreview | None = None
