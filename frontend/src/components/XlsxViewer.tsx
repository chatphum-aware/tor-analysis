import { useEffect, useMemo, useRef, useState } from "react";

import { parseCellRef } from "../lib/sourceLocator";
import type { Source, SourcePreview } from "../types/schema";

interface XlsxViewerProps {
  preview: SourcePreview;
  selectedSource: Source | null;
}

/**
 * Renders the uploaded spreadsheet so a citation can be checked against it.
 *
 * Unlike PdfViewer, this does not re-parse the user's file in the browser: the
 * backend already parsed the workbook with openpyxl to build the prompt text,
 * so it ships a compact cell grid in the response. That avoids pulling an
 * XLSX parser (and its Node-oriented transitive deps) into the bundle just to
 * re-derive data the server already has.
 *
 * Highlighting is exact here, not best-effort as it is for PDFs: a cell
 * reference like "Sheet1!B5" identifies one cell unambiguously, so there's no
 * substring matching to get wrong.
 */
export function XlsxViewer({ preview, selectedSource }: XlsxViewerProps) {
  const target = parseCellRef(selectedSource);
  const [activeSheet, setActiveSheet] = useState(preview.sheets[0]?.name ?? "");
  const cellRef = useRef<HTMLTableCellElement | null>(null);

  // Selecting a citation on another sheet should switch to that sheet.
  useEffect(() => {
    if (target && preview.sheets.some((s) => s.name === target.sheet)) {
      setActiveSheet(target.sheet);
    }
  }, [target?.sheet, target?.cell, preview.sheets]);

  useEffect(() => {
    cellRef.current?.scrollIntoView({ block: "center", inline: "center" });
  }, [target?.sheet, target?.cell, activeSheet]);

  const sheet = preview.sheets.find((s) => s.name === activeSheet) ?? preview.sheets[0];

  // Cells arrive as a flat {ref, value} list; lay them out by parsing A1 refs
  // into column letters and row numbers, keeping the spreadsheet's own shape
  // so a person sees roughly what they'd see in Excel.
  const grid = useMemo(() => {
    if (!sheet) return null;
    const parsed = sheet.cells
      .map((c) => {
        const m = /^([A-Z]+)(\d+)$/.exec(c.ref);
        return m ? { col: m[1], row: Number(m[2]), ref: c.ref, value: c.value } : null;
      })
      .filter((c): c is NonNullable<typeof c> => c !== null);
    const cols = [...new Set(parsed.map((c) => c.col))].sort(
      (a, b) => a.length - b.length || a.localeCompare(b),
    );
    const rows = [...new Set(parsed.map((c) => c.row))].sort((a, b) => a - b);
    const byRef = new Map(parsed.map((c) => [c.ref, c.value]));
    return { cols, rows, byRef };
  }, [sheet]);

  if (!sheet || !grid) {
    return <div className="viewer-pane">ไม่มีข้อมูลให้แสดง</div>;
  }

  return (
    <div className="viewer-pane">
      {preview.sheets.length > 1 && (
        <div className="sheet-tabs">
          {preview.sheets.map((s) => (
            <button
              key={s.name}
              type="button"
              className={s.name === sheet.name ? "sheet-tab sheet-tab-active" : "sheet-tab"}
              onClick={() => setActiveSheet(s.name)}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {sheet.truncated && (
        <p className="viewer-note">
          ⚠️ ชีทนี้มีเซลล์มากกว่าที่แสดงได้ — ส่วนที่แสดงอยู่ไม่ครบทั้งชีท
        </p>
      )}

      <div className="sheet-scroll">
        <table className="sheet-grid">
          <thead>
            <tr>
              <th />
              {grid.cols.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.rows.map((row) => (
              <tr key={row}>
                <th>{row}</th>
                {grid.cols.map((col) => {
                  const ref = `${col}${row}`;
                  const isTarget = target !== null && target.sheet === sheet.name && target.cell === ref;
                  return (
                    <td
                      key={ref}
                      ref={isTarget ? cellRef : undefined}
                      className={isTarget ? "sheet-cell sheet-cell-active" : "sheet-cell"}
                      title={ref}
                    >
                      {grid.byRef.get(ref) ?? ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
