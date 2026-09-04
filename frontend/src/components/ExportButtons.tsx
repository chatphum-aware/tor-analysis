import { useState } from "react";

import { exportCsv } from "../api/client";
import type { TORDocument } from "../types/schema";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ExportButtons({ doc, baseName }: { doc: TORDocument; baseName: string }) {
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);

  const handleExportJson = () => {
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
    downloadBlob(blob, `${baseName}.json`);
  };

  const handleExportCsv = async () => {
    setIsExportingCsv(true);
    setCsvError(null);
    try {
      const blob = await exportCsv(doc);
      downloadBlob(blob, `${baseName}.csv`);
    } catch (err) {
      setCsvError(err instanceof Error ? err.message : "ส่งออก CSV ไม่สำเร็จ");
    } finally {
      setIsExportingCsv(false);
    }
  };

  return (
    <div>
      <div className="mb-4 flex gap-2">
        <button className="btn-secondary" onClick={handleExportJson}>
          ดาวน์โหลด JSON
        </button>
        <button className="btn-secondary" onClick={handleExportCsv} disabled={isExportingCsv}>
          {isExportingCsv ? "กำลังสร้าง CSV..." : "ดาวน์โหลด CSV"}
        </button>
      </div>
      {csvError && <div className="error-banner">{csvError}</div>}
    </div>
  );
}
