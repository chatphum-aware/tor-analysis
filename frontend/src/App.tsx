import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, extractDocument } from "./api/client";
import { ExportButtons } from "./components/ExportButtons";
import { PdfViewer } from "./components/PdfViewer";
import { ResultTable } from "./components/ResultTable";
import { ScannedNotice } from "./components/ScannedNotice";
import { UploadPane } from "./components/UploadPane";
import { UsageFooter } from "./components/UsageFooter";
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

  const isScannedError = mutation.error instanceof ApiError && mutation.error.status === 422;

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>TOR Analyzer</h1>
      </header>

      <div className="app-body">
        {!mutation.data && !isScannedError && (
          <UploadPane
            onSubmit={handleSubmit}
            isPending={mutation.isPending}
            errorMessage={
              mutation.error && !isScannedError
                ? mutation.error instanceof ApiError
                  ? mutation.error.message
                  : "เกิดข้อผิดพลาดที่ไม่คาดคิด"
                : null
            }
          />
        )}

        {isScannedError && mutation.error instanceof ApiError && (
          <ScannedNotice message={mutation.error.message} onReset={handleReset} />
        )}

        {mutation.data && file && (
          <div className="results-layout">
            <div className="results-pane">
              <ExportButtons doc={mutation.data} baseName={file.name.replace(/\.pdf$/i, "")} />
              <ResultTable doc={mutation.data} selectedSource={selectedSource} onSelectSource={setSelectedSource} />
            </div>
            <PdfViewer
              file={file}
              targetPage={selectedSource?.page ?? null}
              targetQuote={selectedSource?.quote ?? null}
            />
          </div>
        )}
      </div>

      {mutation.data && <UsageFooter meta={mutation.data.extraction_meta} />}
    </div>
  );
}
