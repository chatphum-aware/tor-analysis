import type { TORDocument } from "../types/schema";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readErrorDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    return typeof body?.detail === "string" ? body.detail : resp.statusText;
  } catch {
    return resp.statusText;
  }
}

export async function extractDocument(file: File): Promise<TORDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const resp = await fetch(`${API_BASE}/api/extract`, { method: "POST", body: formData });
  if (!resp.ok) {
    throw new ApiError(resp.status, await readErrorDetail(resp));
  }
  return resp.json() as Promise<TORDocument>;
}

export async function exportCsv(doc: TORDocument): Promise<Blob> {
  const resp = await fetch(`${API_BASE}/api/export/csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await readErrorDetail(resp));
  }
  return resp.blob();
}
