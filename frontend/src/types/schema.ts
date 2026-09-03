// Hand-mirrored from backend/app/models/schema.py (TORDocument, the final
// response shape). Kept in sync manually for v0.1 -- no codegen pipeline,
// so a backend schema change must be reflected here by hand. Small enough
// project that this is the smallest correct approach; revisit only if the
// two start drifting in practice.

export type Confidence = "high" | "medium" | "low";

export type ProcurementMethod = "e-bidding" | "คัดเลือก" | "เฉพาะเจาะจง";

export type KeyDateType =
  | "ขอรับเอกสาร"
  | "ชี้แจงรายละเอียด"
  | "ยื่นข้อเสนอ"
  | "เสนอราคา"
  | "ประกาศผล";

export type QualificationCategory =
  | "ทุนจดทะเบียน"
  | "ผลงานที่ผ่านมา"
  | "ใบอนุญาต"
  | "บุคลากร"
  | "เครื่องจักร"
  | "มาตรฐาน"
  | "อื่น ๆ";

export type QualificationOperator = "ไม่น้อยกว่า" | "ไม่เกิน" | "เท่ากับ" | "อย่างน้อย";

export type SourceKind =
  | "text_page"
  | "vision_page"
  | "paragraph"
  | "table_cell_docx"
  | "cell_xlsx";

/** Hand-mirrors `Source` in backend/app/models/schema.py. Which locator
 * fields are non-null depends on `kind` (the backend validator enforces
 * this) — use the helpers in src/lib/sourceLocator.ts rather than reading
 * `page` directly, since it is null for DOCX/XLSX sources. */
export interface Source {
  kind: SourceKind;
  quote: string;
  /** Set for text_page/vision_page; null for the DOCX/XLSX kinds. */
  page: number | null;
  /** Set for paragraph ("para:12"), table_cell_docx ("t1:r3:c2") and
   * cell_xlsx ("Sheet1!B5"); null for the page kinds. Format is
   * regex-enforced backend-side, so parsing here is safe. */
  ref: string | null;
}

export interface Sourced<T> {
  value: T | null;
  source: Source | null;
  confidence: Confidence;
  reason: string | null;
}

export interface KeyDate {
  type: Sourced<KeyDateType>;
  date_be: Sourced<string>;
  time: Sourced<string>;
  location: Sourced<string>;
  date_ce: string;
}

export interface BondInfo {
  amount: Sourced<number>;
  percent_stated: Sourced<number>;
  accepted_forms: Sourced<string[]>;
}

export interface QualificationItem {
  text: Sourced<string>;
  category: Sourced<QualificationCategory>;
  operator: Sourced<QualificationOperator>;
  value: Sourced<number>;
  unit: Sourced<string>;
}

export interface DeliverableItem {
  phase: Sourced<string>;
  description: Sourced<string>;
  days_from_signing: Sourced<number>;
  payment_percent: Sourced<number>;
}

export interface PenaltyInfo {
  rate_percent_per_day: Sourced<number>;
  cap_percent: Sourced<number>;
}

export interface EvaluationCriteria {
  method: Sourced<string>;
  price_weight: Sourced<number>;
  technical_weight: Sourced<number>;
  sub_criteria: Sourced<string[]>;
}

export interface ContactInfo {
  name_redacted: Sourced<string>;
  department: Sourced<string>;
  phone: Sourced<string>;
  email: Sourced<string>;
}

export interface RiskFlag {
  text: string;
  origin: "model" | "derived";
  source: Source | null;
}

export interface ExtractionUsage {
  input_tokens: number;
  output_tokens: number;
  cache_write_tokens: number;
  cached_read_tokens: number;
}

export interface ExtractionCost {
  usd: number;
  thb: number;
  usd_thb_rate: number;
  rate_source_date: string;
  is_estimate: boolean;
}

export type DocumentKind = "pdf" | "docx" | "xlsx";

export interface SheetCell {
  ref: string; // A1 notation within its sheet, e.g. "B5"
  value: string;
}

export interface SheetPreview {
  name: string;
  cells: SheetCell[];
  /** The sheet had more populated cells than the preview cap. */
  truncated: boolean;
}

export interface DocxBlock {
  ref: string; // "para:12" or "t1:r3:c2" -- matches Source.ref verbatim
  text: string;
  kind: "paragraph" | "table_cell";
}

/** Enough of the source document to render it and highlight a citation.
 * Only sent for formats the browser can't render itself (XLSX); null for
 * PDFs, which render from the user's own file via react-pdf. */
export interface SourcePreview {
  document_kind: DocumentKind;
  /** Exactly one of these is populated, per document_kind. */
  sheets: SheetPreview[];
  blocks: DocxBlock[];
}

export interface ExtractionMeta {
  /** Which format the upload actually was, decided server-side by magic
   * bytes. The page-shaped fields below are null for formats with no pages. */
  document_kind: DocumentKind;
  page_count: number | null;
  usable_text_page_ratio: number | null;
  image_only_pages: number[] | null;
  paragraph_count: number | null;
  sheet_names: string[] | null;
  provider: string;
  model: string;
  pricing_as_of: string;
  extracted_at: string;
  duration_ms: number;
  usage: ExtractionUsage;
  cost: ExtractionCost;
}

export interface TORDocument {
  project_name: Sourced<string>;
  project_id: Sourced<string>;
  agency: Sourced<string>;
  announcement_date: Sourced<string>;
  procurement_method: Sourced<ProcurementMethod>;
  budget_amount: Sourced<number>;
  median_price: Sourced<number>;
  key_dates: KeyDate[];
  bid_bond: BondInfo;
  bid_bond_percent_of_budget: number | null;
  contract_bond: BondInfo;
  contract_bond_percent_of_budget: number | null;
  warranty_bond: BondInfo;
  warranty_bond_percent_of_budget: number | null;
  qualifications: QualificationItem[];
  deliverables: DeliverableItem[];
  penalty: PenaltyInfo;
  required_documents: Sourced<string>[];
  evaluation_criteria: EvaluationCriteria;
  risk_flags: RiskFlag[];
  contact: ContactInfo;
  extraction_meta: ExtractionMeta;
  source_preview: SourcePreview | null;
}
