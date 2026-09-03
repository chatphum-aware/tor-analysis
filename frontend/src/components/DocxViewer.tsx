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
    return <div className="viewer-pane">ไม่มีข้อความให้แสดง</div>;
  }

  return (
    <div className="viewer-pane">
      <div className="doc-scroll">
        {preview.blocks.map((block) => {
          const isTarget = targetRef !== null && block.ref === targetRef;
          return (
            <div
              key={block.ref}
              ref={isTarget ? activeEl : undefined}
              className={[
                "doc-block",
                block.kind === "table_cell" && "doc-block-cell",
                isTarget && "doc-block-active",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <span className="doc-block-ref" title={block.ref}>
                {block.ref}
              </span>
              <span className="doc-block-text">{block.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
