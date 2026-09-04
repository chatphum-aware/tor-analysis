import { useRef, useState, type DragEvent } from "react";

interface UploadPaneProps {
  onSubmit: (file: File) => void;
  isPending: boolean;
  errorMessage: string | null;
}

// A hint for the file picker only -- the backend decides the real format
// from magic bytes (app/ingest/detect.py), never this or the browser-reported
// MIME type. XLSX is deliberately absent: the backend gates it behind
// TOR_ENABLE_XLSX (see ingest/dispatch.py), so offering it here would let
// users pick a file that comes back 415. Add
// ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
// when that flag is turned on.
const ACCEPTED_TYPES =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function UploadPane({ onSubmit, isPending, errorMessage }: UploadPaneProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const openFilePicker = () => {
    if (!isPending) inputRef.current?.click();
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!isPending) setIsDragActive(true);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragActive(false);
    if (isPending) return;
    const dropped = e.dataTransfer.files?.[0] ?? null;
    if (dropped) setFile(dropped);
  };

  return (
    <div className="m-auto max-w-[480px] p-8 text-center">
      <h2 className="mt-0 mb-3 text-2xl font-bold">TOR Analyzer</h2>
      <p>อัปโหลดเอกสาร TOR / ประกาศประกวดราคา (PDF หรือ Word .docx) เพื่อดึงข้อมูลสำคัญ</p>

      <div
        className={[
          "my-5 rounded-xl border-2 border-dashed border-border bg-bg-subtle px-5 py-8 transition-colors",
          isPending ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-accent",
          isDragActive && "border-accent bg-[#eaf0fd]",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={openFilePicker}
        onDragOver={handleDragOver}
        onDragLeave={() => setIsDragActive(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={ACCEPTED_TYPES}
          disabled={isPending}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <div className="mb-2 text-[2rem]" aria-hidden="true">
          📄
        </div>
        {file ? (
          <p className="my-1 font-semibold break-words">{file.name}</p>
        ) : (
          <>
            <p className="my-1">
              <strong>คลิกเพื่อเลือกไฟล์</strong> หรือลากไฟล์มาวางที่นี่
            </p>
            <p className="m-0 text-[0.85rem] text-text-muted">รองรับ PDF และ Word (.docx)</p>
          </>
        )}
      </div>

      <button
        className="rounded-md border-none bg-accent px-5 py-2.5 text-[0.95rem] text-white"
        disabled={!file || isPending}
        onClick={() => file && onSubmit(file)}
      >
        {isPending ? "กำลังวิเคราะห์... (อาจใช้เวลาถึง 1 นาที)" : "วิเคราะห์เอกสาร"}
      </button>
      {errorMessage && <div className="error-banner">{errorMessage}</div>}
    </div>
  );
}
