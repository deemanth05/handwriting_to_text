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
  verifiedLineItems: any[] = [],
  verifiedLedgerItems: any[] = [],
  verifiedBy: string = "human-reviewer"
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      verified_fields: verifiedFields,
      verified_line_items: verifiedLineItems,
      verified_ledger_items: verifiedLedgerItems,
      verified_by: verifiedBy,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Verification failed" }));
    throw new Error(err.detail || `Server returned ${res.status}`);
  }

  return res.json();
}

export function getDocumentImageUrl(documentId: string, page: number = 1): string {
  if (page > 1) {
    return `${API_BASE}/documents/${documentId}/image?page=${page}`;
  }
  return `${API_BASE}/documents/${documentId}/image`;
}

export interface RuntimeProbeReport {
  timestamp: number;
  runtimes: {
    ollama: {
      runtime: string;
      status: "ONLINE" | "OFFLINE" | "ERROR";
      latency_ms?: number;
      models?: string[];
      vision_models?: string[];
      has_vision?: boolean;
    };
    lmstudio: {
      runtime: string;
      status: "ONLINE" | "OFFLINE" | "ERROR";
      latency_ms?: number;
      models?: string[];
      has_vision?: boolean;
    };
    freellm: {
      runtime: string;
      status: "ONLINE" | "OFFLINE" | "ERROR";
      latency_ms?: number;
      models_count?: number;
      has_vision?: boolean;
    };
    surya_local: {
      runtime: string;
      status: string;
      engine?: string;
      languages?: string[];
    };
    rapidocr_local: {
      runtime: string;
      status: string;
      engine?: string;
    };
  };
  circuit_breakers?: Record<
    string,
    {
      state: string;
      can_execute: boolean;
      failure_count: number;
      remaining_cooldown_seconds: number;
      last_error?: string | null;
    }
  >;
}

export async function checkRuntimesHealth(): Promise<RuntimeProbeReport> {
  const res = await fetch(`${API_BASE}/health/runtimes`);
  if (!res.ok) {
    throw new Error("Failed to fetch runtime health");
  }
  return res.json();
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

export async function downloadDocumentExport(
  documentId: string,
  format: "tally" | "excel" | "gst"
): Promise<void> {
  const endpoint = `${API_BASE}/documents/${documentId}/export/${format}`;
  const res = await fetch(endpoint);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Export failed" }));
    throw new Error(err.detail || `Export failed with status ${res.status}`);
  }

  const disposition = res.headers.get("Content-Disposition");
  let filename = `document_${documentId}.${
    format === "tally" ? "xml" : format === "excel" ? "xlsx" : "json"
  }`;
  if (disposition && disposition.includes("filename=")) {
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
  }

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}
