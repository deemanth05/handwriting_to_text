export type DocumentType = "INVOICE" | "PRESCRIPTION" | "KHATA_LEDGER" | "GENERAL";

export interface ExtractedField<T = any> {
  value: T | null;
  confidence: number;
  agreement: string;
  candidates: Record<string, any>;
  needs_review: boolean;
  bounding_box?: number[] | null;
}

export interface LineItem {
  row_id: number;
  description: ExtractedField<string>;
  quantity: ExtractedField<number>;
  unit_price: ExtractedField<number>;
  line_total: ExtractedField<number>;
  row_math_valid: boolean;
  needs_review: boolean;
}

export interface MathValidationResult {
  is_valid: boolean;
  discrepancy_amount: number;
  error_details: string[];
}

export interface DocumentExtractionResponse {
  document_id: string;
  document_type: DocumentType;
  overall_confidence: number;
  status: "PROCESSED" | "NEEDS_REVIEW" | "VERIFIED";
  math_validation: MathValidationResult;
  fields: Record<string, ExtractedField<any>>;
  line_items: LineItem[];
  processing_time_ms: number;
  models_participated: string[];
}

export interface DocumentListItem {
  id: string;
  filename: string;
  document_type: DocumentType;
  overall_confidence: number;
  math_valid: boolean;
  status: string;
  created_at: string | null;
}
