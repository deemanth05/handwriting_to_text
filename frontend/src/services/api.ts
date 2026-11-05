import {
  BenchmarkSummaryResponse,
  DocumentDiffResponse,
  DocumentExtractionResponse,
  DocumentListItem,
  DocumentType,
} from "../types/document";

const API_BASE = "/api/v1";

export async function extractDocument(
  file: File,
  docType: DocumentType
): Promise<DocumentExtractionResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("doc_type", docType);

  const res = await fetch(`${API_BASE}/extract`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Extraction failed" }));
    throw new Error(err.detail || `Server returned ${res.status}`);
  }

  return res.json();
}

export async function getDocument(documentId: string): Promise<DocumentExtractionResponse> {
  const res = await fetch(`${API_BASE}/documents/${documentId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch document ${documentId}`);
  }
  return res.json();
}

export async function listDocuments(): Promise<DocumentListItem[]> {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) {
    throw new Error("Failed to list documents");
  }
  return res.json();
}

export async function verifyDocument(
  documentId: string,
  verifiedFields: Record<string, any>,
  verifiedLineItems: any[],
  verifiedBy: string = "human-reviewer"
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      verified_fields: verifiedFields,
      verified_line_items: verifiedLineItems,
      verified_by: verifiedBy,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Verification failed" }));
    throw new Error(err.detail || `Server returned ${res.status}`);
  }

  return res.json();
}

export function getDocumentImageUrl(documentId: string): string {
  return `${API_BASE}/documents/${documentId}/image`;
}

export async function checkFreeLLMHealth(): Promise<any> {
  const res = await fetch(`${API_BASE}/health/freellmapi`);
  return res.json();
}

export async function getBenchmarkSummary(): Promise<BenchmarkSummaryResponse> {
  const res = await fetch(`${API_BASE}/benchmarks/summary`);
  if (!res.ok) {
    throw new Error("Failed to fetch benchmark summary");
  }
  return res.json();
}

export async function getDocumentDiff(documentId: string): Promise<DocumentDiffResponse> {
  const res = await fetch(`${API_BASE}/benchmarks/documents/${documentId}/diff`);
  if (!res.ok) {
    throw new Error(`Failed to fetch diff for document ${documentId}`);
  }
  return res.json();
}
