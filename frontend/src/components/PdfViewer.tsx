import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface PdfViewerProps {
  file: File;
  targetPage: number | null;
  targetQuote: string | null;
}

// Best-effort highlighting: the schema carries page + quote text (what the
// LLM cited), not bounding boxes -- there was never a bbox in the pipeline
// past Step 1's internal TextBlock. react-pdf's text layer is independently
// laid out by pdf.js, so instead of coordinate matching we normalize both
// strings (collapse whitespace, NFC) and highlight any text-layer item
// whose content is a substring of the quote. This won't catch every case
// (a quote spanning multiple oddly-segmented items may only partially
// highlight), but it needs no extra data from the backend and degrades
// gracefully -- worst case, the page still jumps to the right place even
// if the highlight itself misses.
function normalize(s: string): string {
  return s.normalize("NFC").replace(/\s+/g, " ").trim();
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Tailwind's content scanner picks up class names inside plain text, so this
// literal HTML string still gets its utility classes generated even though
// it's never parsed as JSX (see customTextRenderer below).
const HIGHLIGHT_CLASS = "bg-[rgba(255,224,102,0.55)] text-inherit mix-blend-multiply";

export function PdfViewer({ file, targetPage, targetQuote }: PdfViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    if (targetPage !== null) setCurrentPage(targetPage);
  }, [targetPage, targetQuote]);

  const normalizedQuote = targetQuote ? normalize(targetQuote) : null;

  return (
    <div className="viewer-pane">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-[0.9rem]">
        <button
          className="btn-secondary"
          disabled={currentPage <= 1}
          onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
        >
          ก่อนหน้า
        </button>
        <span>
          หน้า {currentPage} {numPages ? `/ ${numPages}` : ""}
        </span>
        <button
          className="btn-secondary"
          disabled={!numPages || currentPage >= numPages}
          onClick={() => setCurrentPage((p) => (numPages ? Math.min(numPages, p + 1) : p))}
        >
          ถัดไป
        </button>
      </div>
      <div className="flex flex-1 justify-center overflow-auto bg-bg-subtle p-4">
        <Document
          file={file}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          loading={<p>กำลังโหลด PDF...</p>}
          error={<p>เปิดไฟล์ PDF ไม่ได้</p>}
        >
          <Page
            pageNumber={currentPage}
            renderAnnotationLayer={false}
            customTextRenderer={
              normalizedQuote
                ? ({ str }: { str: string }) => {
                    const normalizedStr = normalize(str);
                    if (normalizedStr.length > 0 && normalizedQuote.includes(normalizedStr)) {
                      return `<mark class="${HIGHLIGHT_CLASS}">${escapeHtml(str)}</mark>`;
                    }
                    return escapeHtml(str);
                  }
                : undefined
            }
          />
        </Document>
      </div>
    </div>
  );
}
