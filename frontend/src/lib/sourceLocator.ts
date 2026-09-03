import type { Source } from "../types/schema";

/**
 * Locator helpers for the generalized `Source` shape.
 *
 * A source locates itself either by `page` (PDF kinds) or by a `ref` string
 * (DOCX/XLSX kinds), because "page" is a PDF concept the other formats don't
 * have — a Word page break is a rendering artifact, not a stored fact, and a
 * spreadsheet addresses cells. Which field is set is decided by `kind`, and the
 * backend validator guarantees it, including `ref`'s format — so the parsing
 * below can trust its shape rather than defending against arbitrary strings.
 *
 * Kept in sync by hand with `_format_locator()` in
 * `backend/app/api/export.py` — same convention as `types/schema.ts` mirroring
 * `schema.py`. Change one, change the other.
 */

/** Sources that point at a PDF page, and so can drive the PDF viewer. */
export function isPageLocator(source: Source | null): boolean {
  return source !== null && (source.kind === "text_page" || source.kind === "vision_page");
}

/** True when the value was read off a rendered page image rather than a real
 * text layer — worth surfacing, since the quote is a transcription. */
export function isVisionLocator(source: Source | null): boolean {
  return source !== null && source.kind === "vision_page";
}

/** Parsed XLSX cell reference, for highlighting the exact cell. `ref` is A1
 * notation ("Sheet1!B5"); split on the LAST "!" since a sheet name may
 * contain one. */
export function parseCellRef(source: Source | null): { sheet: string; cell: string } | null {
  if (source === null || source.kind !== "cell_xlsx" || source.ref === null) return null;
  const at = source.ref.lastIndexOf("!");
  if (at === -1) return null;
  return { sheet: source.ref.slice(0, at), cell: source.ref.slice(at + 1) };
}

export function formatLocator(source: Source | null): string {
  if (source === null) return "";
  switch (source.kind) {
    case "text_page":
      return `หน้า ${source.page}`;
    case "vision_page":
      return `หน้า ${source.page} (ภาพสแกน)`;
    case "paragraph":
      // ref is "para:12"
      return `ย่อหน้าที่ ${source.ref?.split(":")[1] ?? ""}`;
    case "table_cell_docx": {
      // ref is "t1:r3:c2"
      const [t, r, c] = (source.ref ?? "").split(":").map((part) => part.slice(1));
      return `ตารางที่ ${t} แถว ${r} คอลัมน์ ${c}`;
    }
    case "cell_xlsx":
      // already readable A1 notation
      return source.ref ?? "";
    default:
      return "";
  }
}

/**
 * Identity for "is this the same citation the user already selected".
 * Compares `kind` first, then the one locator field that kind uses —
 * comparing `page` alone would treat two different DOCX paragraphs as the
 * same source, since both have a null page.
 */
export function isSameSource(a: Source | null, b: Source | null): boolean {
  if (a === null || b === null || a.kind !== b.kind) return false;
  if (a.quote !== b.quote) return false;
  return isPageLocator(a) ? a.page === b.page : a.ref === b.ref;
}
