import { useState } from "react";

interface UploadPaneProps {
  onSubmit: (file: File) => void;
  isPending: boolean;
  errorMessage: string | null;
}

export function UploadPane({ onSubmit, isPending, errorMessage }: UploadPaneProps) {
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="upload-screen">
      <h2>TOR Analyzer</h2>
      <p>อัปโหลดเอกสาร TOR / ประกาศประกวดราคา (PDF หรือ Word .docx) เพื่อดึงข้อมูลสำคัญ</p>
      <input
        type="file"
        // A hint for the file picker only -- the backend decides the real
        // format from magic bytes (app/ingest/detect.py), never this or the
        // browser-reported MIME type. XLSX is deliberately absent: the backend
        // gates it behind TOR_ENABLE_XLSX (see ingest/dispatch.py), so offering
        // it here would let users pick a file that comes back 415. Add
        // ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        // when that flag is turned on.
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button
        className="primary-button"
        disabled={!file || isPending}
        onClick={() => file && onSubmit(file)}
      >
        {isPending ? "กำลังวิเคราะห์... (อาจใช้เวลาถึง 1 นาที)" : "วิเคราะห์เอกสาร"}
      </button>
      {errorMessage && <div className="error-banner">{errorMessage}</div>}
    </div>
  );
}
