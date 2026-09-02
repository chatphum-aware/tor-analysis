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

export interface Source {
  page: number;
  quote: string;
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
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
}

export interface ExtractionCost {
  usd: number;
  thb: number;
  usd_thb_rate: number;
  rate_source_date: string;
  is_estimate: boolean;
}

export interface ExtractionMeta {
  page_count: number;
  usable_text_page_ratio: number;
  image_only_pages: number[];
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
}
