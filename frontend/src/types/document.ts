export type DocumentType = "INVOICE" | "PRESCRIPTION" | "KHATA_LEDGER" | "CASH_BOOK" | "GENERAL";

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
  page_number?: number;
  description: ExtractedField<string>;
  quantity: ExtractedField<number>;
  unit_price: ExtractedField<number>;
  line_total: ExtractedField<number>;
  row_math_valid: boolean;
  needs_review: boolean;
}

export interface LedgerTransactionItem {
  row_id: number;
  page_number?: number;
  entry_date: ExtractedField<string>;
  particulars: ExtractedField<string>;
  voucher_no?: string | null;
  cash_out_debit: ExtractedField<number>;
  cash_in_credit: ExtractedField<number>;
  running_balance: ExtractedField<number>;
  balance_math_valid: boolean;
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
  page_count?: number;
  pages?: Array<{
    page_number: number;
    confidence: number;
    items_count: number;
    math_valid: boolean;
  }>;
  overall_confidence: number;
  status: "PROCESSED" | "NEEDS_REVIEW" | "VERIFIED";
  math_validation: MathValidationResult;
  fields: Record<string, ExtractedField<any>>;
  line_items: LineItem[];
  ledger_items: LedgerTransactionItem[];
  processing_time_ms: number;
  models_participated: string[];
  error_summary?: string | null;
}

export interface DocumentListItem {
  id: string;
  filename: string;
  document_type: DocumentType;
  overall_confidence: number;
  math_valid: boolean;
  page_count?: number;
  status: string;
  created_at: string | null;
}

export interface ModelEvaluationMetric {
  model_name: string;
  exact_match_accuracy: number;
  cer: number;
  total_fields_evaluated: number;
  correct_fields_count: number;
  avg_latency_ms: number;
  math_error_intercept_rate: number;
}

export interface ECEBucket {
  confidence_bin: string;
  avg_confidence: number;
  accuracy: number;
  sample_count: number;
}

export interface BenchmarkSummaryResponse {
  total_documents_processed: number;
  verified_ground_truths_count: number;
  needs_review_count: number;
  models: ModelEvaluationMetric[];
  ensemble_accuracy_gain: number;
  expected_calibration_error: number;
  calibration_curve: ECEBucket[];
}

export interface FieldDiff {
  field_name: string;
  ground_truth_value: any;
  ensemble_value: any;
  ensemble_correct: boolean;
  model_predictions: Record<string, { value: any; correct: boolean; cer: number }>;
}

export interface DocumentDiffResponse {
  document_id: string;
  field_diffs: FieldDiff[];
  line_item_count: number;
  per_model_accuracy: Record<string, number>;
}
