import { Fragment, type ReactNode } from "react";

import { formatLocator, isSameSource } from "../lib/sourceLocator";
import type { Sourced, Source, TORDocument } from "../types/schema";

interface ResultTableProps {
  doc: TORDocument;
  selectedSource: Source | null;
  onSelectSource: (source: Source) => void;
}

const CONFIDENCE_CLASS: Record<Sourced<unknown>["confidence"], string> = {
  high: "bg-high-bg text-high",
  medium: "bg-warn-bg text-medium",
  low: "bg-danger-bg text-low",
};

function ConfidenceBadge({ confidence }: { confidence: Sourced<unknown>["confidence"] }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-px text-[0.75rem] font-semibold ${CONFIDENCE_CLASS[confidence]}`}
    >
      {confidence}
    </span>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") return value.toLocaleString("th-TH");
  return String(value);
}

const CELL_CLASS = "border-b border-bg-subtle px-2 py-1.5 text-left align-top";

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
  const rowClassName = [
    clickable && "cursor-pointer hover:bg-bg-subtle",
    isActive && "bg-[#eaf0fd] shadow-[inset_3px_0_0_var(--color-accent)] hover:bg-[#dfe8fc]",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <tr className={rowClassName} onClick={() => clickable && onSelectSource(sourced.source!)}>
      <td className={`${CELL_CLASS} whitespace-nowrap text-text-muted`}>{label}</td>
      <td className={CELL_CLASS}>
        {sourced.value === null ? (
          <span className="italic text-text-muted">ไม่พบ{sourced.reason ? ` — ${sourced.reason}` : ""}</span>
        ) : (
          formatValue(sourced.value)
        )}
      </td>
      <td className={CELL_CLASS}>
        <ConfidenceBadge confidence={sourced.confidence} />
      </td>
      <td className={`${CELL_CLASS} whitespace-nowrap text-text-muted`}>
        {clickable ? formatLocator(sourced.source) : ""}
      </td>
    </tr>
  );
}

function CalculatedRow({ label, value, note }: { label: string; value: number | null; note?: string }) {
  return (
    <tr>
      <td className={`${CELL_CLASS} whitespace-nowrap text-text-muted`}>{label}</td>
      <td className={CELL_CLASS}>
        {value === null ? (
          <span className="italic text-text-muted">คำนวณไม่ได้{note ? ` — ${note}` : ""}</span>
        ) : (
          `${value.toLocaleString("th-TH")}%`
        )}
      </td>
      <td className={`${CELL_CLASS} whitespace-nowrap text-text-muted`}>คำนวณโดยระบบ</td>
      <td className={CELL_CLASS}></td>
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
    <section className="mb-6">
      <h3 className="mt-4 mb-2 border-b-2 border-border pb-1 text-base font-bold">{title}</h3>
      <table className="w-full border-collapse text-[0.9rem]">
        <thead>
          <tr>
            <th className={`${CELL_CLASS} text-[0.8rem] font-medium text-text-muted`}>ฟิลด์</th>
            <th className={`${CELL_CLASS} text-[0.8rem] font-medium text-text-muted`}>ค่า</th>
            <th className={`${CELL_CLASS} text-[0.8rem] font-medium text-text-muted`}>ความมั่นใจ</th>
            <th className={`${CELL_CLASS} text-[0.8rem] font-medium text-text-muted`}>ที่มา</th>
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
                <td className={`${CELL_CLASS} whitespace-nowrap text-text-muted`}>{`[${i + 1}] วันที่ (ค.ศ.)`}</td>
                <td className={CELL_CLASS}>{kd.date_ce || "-"}</td>
                <td className={`${CELL_CLASS} whitespace-nowrap text-text-muted`}>คำนวณโดยระบบ</td>
                <td className={CELL_CLASS}></td>
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
        <section className="mb-6">
          <h3 className="mt-4 mb-2 border-b-2 border-border pb-1 text-base font-bold">ข้อที่ควรระวัง</h3>
          {doc.risk_flags.map((flag, i) => (
            <div
              key={i}
              className={[
                "mb-2 rounded-md bg-warn-bg px-3 py-2 text-[0.9rem]",
                isSameSource(flag.source, selectedSource) && "shadow-[inset_3px_0_0_var(--color-accent)]",
                flag.source ? "cursor-pointer" : "cursor-default",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => flag.source && onSelectSource(flag.source)}
            >
              <span className="mr-1.5 text-[0.7rem] uppercase text-text-muted">
                {flag.origin === "model" ? "พบในเอกสาร" : "ตรวจพบโดยระบบ"}
              </span>
              {flag.text}
              {flag.source && <span className="whitespace-nowrap text-text-muted"> ({formatLocator(flag.source)})</span>}
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
