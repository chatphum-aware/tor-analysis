import { Fragment, type ReactNode } from "react";

import type { Sourced, Source, TORDocument } from "../types/schema";

interface ResultTableProps {
  doc: TORDocument;
  selectedSource: Source | null;
  onSelectSource: (source: Source) => void;
}

function isSameSource(a: Source | null, b: Source | null): boolean {
  return a !== null && b !== null && a.page === b.page && a.quote === b.quote;
}

function ConfidenceBadge({ confidence }: { confidence: Sourced<unknown>["confidence"] }) {
  return <span className={`confidence-badge confidence-${confidence}`}>{confidence}</span>;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") return value.toLocaleString("th-TH");
  return String(value);
}

function SourcedRow({
  label,
  sourced,
  selectedSource,
  onSelectSource,
}: {
  label: string;
  sourced: Sourced<unknown>;
  selectedSource: Source | null;
  onSelectSource: (source: Source) => void;
}) {
  const clickable = sourced.source !== null;
  const isActive = clickable && isSameSource(sourced.source, selectedSource);
  const rowClassName = [clickable && "row-clickable", isActive && "row-active"].filter(Boolean).join(" ");
  return (
    <tr className={rowClassName} onClick={() => clickable && onSelectSource(sourced.source!)}>
      <td className="field-label">{label}</td>
      <td>
        {sourced.value === null ? (
          <span className="null-value">ไม่พบ{sourced.reason ? ` — ${sourced.reason}` : ""}</span>
        ) : (
          formatValue(sourced.value)
        )}
      </td>
      <td>
        <ConfidenceBadge confidence={sourced.confidence} />
      </td>
      <td className="field-label">{clickable ? `หน้า ${sourced.source!.page}` : ""}</td>
    </tr>
  );
}

function CalculatedRow({ label, value, note }: { label: string; value: number | null; note?: string }) {
  return (
    <tr>
      <td className="field-label">{label}</td>
      <td>{value === null ? <span className="null-value">คำนวณไม่ได้{note ? ` — ${note}` : ""}</span> : `${value.toLocaleString("th-TH")}%`}</td>
      <td className="field-label">คำนวณโดยระบบ</td>
      <td></td>
    </tr>
  );
}

function SectionTable({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="result-section">
      <h3>{title}</h3>
      <table className="result-table">
        <thead>
          <tr>
            <th>ฟิลด์</th>
            <th>ค่า</th>
            <th>ความมั่นใจ</th>
            <th>ที่มา</th>
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </section>
  );
}

export function ResultTable({ doc, selectedSource, onSelectSource }: ResultTableProps) {
  return (
    <div>
      <SectionTable title="ข้อมูลพื้นฐาน">
        <SourcedRow label="ชื่อโครงการ" sourced={doc.project_name} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="เลขที่โครงการ" sourced={doc.project_id} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="หน่วยงาน" sourced={doc.agency} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="วันที่ประกาศ" sourced={doc.announcement_date} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="วิธีจัดซื้อจัดจ้าง" sourced={doc.procurement_method} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="วงเงินงบประมาณ" sourced={doc.budget_amount} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="ราคากลาง" sourced={doc.median_price} onSelectSource={onSelectSource} selectedSource={selectedSource} />
      </SectionTable>

      {doc.key_dates.length > 0 && (
        <SectionTable title="วันสำคัญ">
          {doc.key_dates.map((kd, i) => (
            <Fragment key={i}>
              <SourcedRow label={`[${i + 1}] ประเภท`} sourced={kd.type} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] วันที่ (พ.ศ.)`} sourced={kd.date_be} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <tr>
                <td className="field-label">{`[${i + 1}] วันที่ (ค.ศ.)`}</td>
                <td>{kd.date_ce || "-"}</td>
                <td className="field-label">คำนวณโดยระบบ</td>
                <td></td>
              </tr>
              <SourcedRow label={`[${i + 1}] เวลา`} sourced={kd.time} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] สถานที่`} sourced={kd.location} onSelectSource={onSelectSource} selectedSource={selectedSource} />
            </Fragment>
          ))}
        </SectionTable>
      )}

      <SectionTable title="หลักประกันการเสนอราคา">
        <SourcedRow label="จำนวนเงิน" sourced={doc.bid_bond.amount} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="ร้อยละที่ระบุในเอกสาร" sourced={doc.bid_bond.percent_stated} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="รูปแบบที่ยอมรับ" sourced={doc.bid_bond.accepted_forms} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <CalculatedRow label="% ของวงเงินงบประมาณ" value={doc.bid_bond_percent_of_budget} />
      </SectionTable>

      <SectionTable title="หลักประกันสัญญา">
        <SourcedRow label="จำนวนเงิน" sourced={doc.contract_bond.amount} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="ร้อยละที่ระบุในเอกสาร" sourced={doc.contract_bond.percent_stated} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="รูปแบบที่ยอมรับ" sourced={doc.contract_bond.accepted_forms} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <CalculatedRow label="% ของวงเงินงบประมาณ" value={doc.contract_bond_percent_of_budget} />
      </SectionTable>

      <SectionTable title="หลักประกันผลงาน">
        <SourcedRow label="จำนวนเงิน" sourced={doc.warranty_bond.amount} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="ร้อยละที่ระบุในเอกสาร" sourced={doc.warranty_bond.percent_stated} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="รูปแบบที่ยอมรับ" sourced={doc.warranty_bond.accepted_forms} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <CalculatedRow label="% ของวงเงินงบประมาณ" value={doc.warranty_bond_percent_of_budget} />
      </SectionTable>

      {doc.qualifications.length > 0 && (
        <SectionTable title="คุณสมบัติผู้เสนอราคา">
          {doc.qualifications.map((q, i) => (
            <Fragment key={i}>
              <SourcedRow label={`[${i + 1}] ข้อความ`} sourced={q.text} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] หมวดหมู่`} sourced={q.category} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] เงื่อนไข`} sourced={q.operator} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] ค่า`} sourced={q.value} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] หน่วย`} sourced={q.unit} onSelectSource={onSelectSource} selectedSource={selectedSource} />
            </Fragment>
          ))}
        </SectionTable>
      )}

      {doc.deliverables.length > 0 && (
        <SectionTable title="งวดงาน / สิ่งที่ต้องส่งมอบ">
          {doc.deliverables.map((d, i) => (
            <Fragment key={i}>
              <SourcedRow label={`[${i + 1}] งวด`} sourced={d.phase} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] รายละเอียด`} sourced={d.description} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] วันนับจากเซ็นสัญญา`} sourced={d.days_from_signing} onSelectSource={onSelectSource} selectedSource={selectedSource} />
              <SourcedRow label={`[${i + 1}] % การจ่ายเงิน`} sourced={d.payment_percent} onSelectSource={onSelectSource} selectedSource={selectedSource} />
            </Fragment>
          ))}
        </SectionTable>
      )}

      <SectionTable title="ค่าปรับ">
        <SourcedRow label="อัตราค่าปรับต่อวัน (%)" sourced={doc.penalty.rate_percent_per_day} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="เพดานค่าปรับ (%)" sourced={doc.penalty.cap_percent} onSelectSource={onSelectSource} selectedSource={selectedSource} />
      </SectionTable>

      {doc.required_documents.length > 0 && (
        <SectionTable title="เอกสารที่ต้องยื่น">
          {doc.required_documents.map((rd, i) => (
            <SourcedRow key={i} label={`[${i + 1}]`} sourced={rd} onSelectSource={onSelectSource} selectedSource={selectedSource} />
          ))}
        </SectionTable>
      )}

      <SectionTable title="เกณฑ์การประเมิน">
        <SourcedRow label="วิธีประเมิน" sourced={doc.evaluation_criteria.method} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="น้ำหนักราคา (%)" sourced={doc.evaluation_criteria.price_weight} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="น้ำหนักเทคนิค (%)" sourced={doc.evaluation_criteria.technical_weight} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="เกณฑ์ย่อย" sourced={doc.evaluation_criteria.sub_criteria} onSelectSource={onSelectSource} selectedSource={selectedSource} />
      </SectionTable>

      {doc.risk_flags.length > 0 && (
        <section className="result-section">
          <h3>ข้อที่ควรระวัง</h3>
          {doc.risk_flags.map((flag, i) => (
            <div
              key={i}
              className={["risk-flag", isSameSource(flag.source, selectedSource) && "risk-flag-active"]
                .filter(Boolean)
                .join(" ")}
              style={{ cursor: flag.source ? "pointer" : "default" }}
              onClick={() => flag.source && onSelectSource(flag.source)}
            >
              <span className="risk-flag-origin">{flag.origin === "model" ? "พบในเอกสาร" : "ตรวจพบโดยระบบ"}</span>
              {flag.text}
              {flag.source && <span className="field-label"> (หน้า {flag.source.page})</span>}
            </div>
          ))}
        </section>
      )}

      <SectionTable title="ผู้ติดต่อ">
        <SourcedRow label="ตำแหน่ง/หน่วยงาน" sourced={doc.contact.name_redacted} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="ฝ่าย/แผนก" sourced={doc.contact.department} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="เบอร์โทร" sourced={doc.contact.phone} onSelectSource={onSelectSource} selectedSource={selectedSource} />
        <SourcedRow label="อีเมล" sourced={doc.contact.email} onSelectSource={onSelectSource} selectedSource={selectedSource} />
      </SectionTable>
    </div>
  );
}
