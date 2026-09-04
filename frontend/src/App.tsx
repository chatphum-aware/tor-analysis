import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, extractDocument } from "./api/client";
import { ExportButtons } from "./components/ExportButtons";
import { PdfViewer } from "./components/PdfViewer";
import { ResultTable } from "./components/ResultTable";
import { RejectedFileNotice } from "./components/RejectedFileNotice";
import { UploadPane } from "./components/UploadPane";
import { UsageFooter } from "./components/UsageFooter";
import { DocxViewer } from "./components/DocxViewer";
import { XlsxViewer } from "./components/XlsxViewer";
import { isPageLocator } from "./lib/sourceLocator";
import type { Source } from "./types/schema";

export function App() {
  const [file, setFile] = useState<File | null>(null);
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);

  const mutation = useMutation({
    mutationFn: extractDocument,
  });

  const handleSubmit = (selectedFile: File) => {
    setFile(selectedFile);
    setSelectedSource(null);
    mutation.mutate(selectedFile);
  };

  const handleReset = () => {
    setFile(null);
    setSelectedSource(null);
    mutation.reset();
  };

  // A 422 means the file was read but exceeds a bound this tool won't
  // silently work around (too many scanned pages for vision, a spreadsheet/
  // Word doc too large to read in one pass, etc.) -- see api/extract.py's
  // 422 raise sites for the exact cases. Anything else is a generic error.
  const isRejectedError = mutation.error instanceof ApiError && mutation.error.status === 422;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="border-b border-border px-6 py-4">
        <h1 className="m-0 text-xl font-bold">TOR Analyzer</h1>
      </header>

      <div className="flex min-h-0 flex-1 overflow-y-auto">
        {!mutation.data && !isRejectedError && (
          <UploadPane
            onSubmit={handleSubmit}
            isPending={mutation.isPending}
            errorMessage={
              mutation.error && !isRejectedError
                ? mutation.error instanceof ApiError
                  ? mutation.error.message
                  : "เกิดข้อผิดพลาดที่ไม่คาดคิด"
                : null
            }
          />
        )}

        {isRejectedError && mutation.error instanceof ApiError && (
          <RejectedFileNotice message={mutation.error.message} onReset={handleReset} />
        )}

        {mutation.data && file && (
          <div className="flex min-h-0 w-full">
            <div className="min-w-0 flex-[1_1_55%] overflow-y-auto px-5 py-4">
              <div className="mb-3">
                <button className="btn-secondary" onClick={handleReset}>
                  ← กลับไปหน้าอัปโหลด
                </button>
              </div>
              <ExportButtons
                doc={mutation.data}
                baseName={file.name.replace(/\.(pdf|docx|xlsx)$/i, "")}
              />
              <ResultTable doc={mutation.data} selectedSource={selectedSource} onSelectSource={setSelectedSource} />
            </div>
            {/* Which viewer can verify a citation depends on the source
                format: a PDF renders from the user's own file, while a
                spreadsheet renders from the cell grid the backend already
                parsed (see XlsxViewer). */}
            {mutation.data.source_preview?.document_kind === "xlsx" ? (
              <XlsxViewer
                preview={mutation.data.source_preview}
                selectedSource={selectedSource}
              />
            ) : mutation.data.source_preview?.document_kind === "docx" ? (
              <DocxViewer
                preview={mutation.data.source_preview}
                selectedSource={selectedSource}
              />
            ) : (
              <PdfViewer
                file={file}
                targetPage={isPageLocator(selectedSource) ? selectedSource!.page : null}
                targetQuote={selectedSource?.quote ?? null}
              />
            )}
          </div>
        )}
      </div>

      {mutation.data && <UsageFooter meta={mutation.data.extraction_meta} />}
    </div>
  );
}
