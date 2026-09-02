import type { ExtractionMeta } from "../types/schema";

export function UsageFooter({ meta }: { meta: ExtractionMeta }) {
  const { usage, cost } = meta;
  return (
    <div className="usage-footer">
      <span>
        token: input {usage.input_tokens.toLocaleString("th-TH")} · output{" "}
        {usage.output_tokens.toLocaleString("th-TH")} · cache write{" "}
        {usage.cache_creation_input_tokens.toLocaleString("th-TH")} · cache read{" "}
        {usage.cache_read_input_tokens.toLocaleString("th-TH")}
      </span>
      <span>
        ค่าใช้จ่ายประมาณการ: ${cost.usd.toFixed(4)} (~฿{cost.thb.toFixed(2)} @ {cost.usd_thb_rate}{" "}
        ณ {cost.rate_source_date}) · โมเดล {meta.model} · {(meta.duration_ms / 1000).toFixed(1)}{" "}
        วินาที
      </span>
    </div>
  );
}
