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
      <p>อัปโหลดเอกสาร TOR / ประกาศประกวดราคา (PDF) เพื่อดึงข้อมูลสำคัญ</p>
      <input
        type="file"
        accept="application/pdf"
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
