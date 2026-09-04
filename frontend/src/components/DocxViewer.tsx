import { useEffect, useRef } from "react";

import type { Source, SourcePreview } from "../types/schema";

interface DocxViewerProps {
  preview: SourcePreview;
  selectedSource: Source | null;
}

/**
 * Renders the uploaded Word document so a citation can be checked against it.
 *
 * Like XlsxViewer, this renders what the backend already parsed rather than
 * re-parsing the file in the browser — no DOCX/HTML-conversion library in the
 * bundle, and the block refs shown here are the exact same ones the model
 * cited, so highlighting is exact rather than the PDF viewer's best-effort
 * quote matching.
 *
 * Blocks arrive in document order, paragraphs and table cells interleaved,
 * matching how the model read the document.
 */
export function DocxViewer({ preview, selectedSource }: DocxViewerProps) {
  const targetRef = selectedSource?.ref ?? null;
  const activeEl = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    activeEl.current?.scrollIntoView({ block: "center" });
  }, [targetRef]);

  if (preview.blocks.length === 0) {
    return <div className="viewer-pane overflow-hidden">ไม่มีข้อความให้แสดง</div>;
  }

  return (
    <div className="viewer-pane overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
        {preview.blocks.map((block) => {
          const isTarget = targetRef !== null && block.ref === targetRef;
          return (
            <div
              key={block.ref}
              ref={isTarget ? activeEl : undefined}
              className={[
                "flex scroll-mt-10 gap-2.5 rounded p-[5px_6px] text-[0.88rem] leading-[1.6]",
                block.kind === "table_cell" && "border-l-[3px] border-border bg-[#f7f7f8]",
                isTarget && "bg-highlight outline outline-2 outline-accent",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <span
                className="flex-none pt-[3px] font-mono text-[0.7rem] text-text-muted select-all"
                title={block.ref}
              >
                {block.ref}
              </span>
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{block.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
