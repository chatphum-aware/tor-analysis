interface RejectedFileNoticeProps {
  message: string;
  onReset: () => void;
}

/**
 * Shown for a 422 response -- the file was read successfully but exceeds a
 * bound this tool won't silently work around (too many scanned pages for
 * vision, too large a spreadsheet/Word document to read in one pass, etc.).
 *
 * Deliberately shows only the backend's own message, not a second guess at
 * what went wrong: which of those cases applies varies by upload, and the
 * backend already composed the specific, correct explanation (see the 422
 * raise sites in app/api/extract.py) -- restating a generic guess here would
 * risk contradicting it.
 */
export function RejectedFileNotice({ message, onReset }: RejectedFileNoticeProps) {
  return (
    <div className="scanned-notice">
      <strong>⚠️ ไม่สามารถประมวลผลไฟล์นี้ได้</strong>
      <p>{message}</p>
      <button className="secondary-button" onClick={onReset}>
        ลองไฟล์อื่น
      </button>
    </div>
  );
}
