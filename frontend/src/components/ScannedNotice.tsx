interface ScannedNoticeProps {
  message: string;
  onReset: () => void;
}

export function ScannedNotice({ message, onReset }: ScannedNoticeProps) {
  return (
    <div className="scanned-notice">
      <strong>⚠️ ไม่รองรับไฟล์นี้</strong>
      <p>{message}</p>
      <p className="scanned-notice-hint">
        v0.1 ยังไม่รองรับ OCR — เอกสารต้องมีข้อความที่เลือก/คัดลอกได้ (ไม่ใช่ภาพสแกนล้วน)
      </p>
      <button className="secondary-button" onClick={onReset}>
        ลองไฟล์อื่น
      </button>
    </div>
  );
}
