"""Isolated System Prompts & Extraction Schemas.

All prompts are strictly centralized here to keep route handlers and services clean.
Instructs models on Indian regional scripts, handwriting quirks, and numeric formats.
"""

from backend.app.schemas.document import DocumentType

SYSTEM_INSTRUCTION_BASE = """You are an expert document vision extractor specialized in handwritten and printed Indian documents (invoices, medical prescriptions, and local business khata ledgers).
The image may contain mixed scripts (English, Hindi, Marathi, Devanagari, Kannada) and Indian numerals (०-९, ೦-೯).

CRITICAL EXTRACTION RULES:
1. Output valid RFC 8259 JSON ONLY. Do not wrap in markdown codeblocks (no ```json). Do not include any explanations.
2. Read handwriting carefully. If numerals are in Devanagari (०-९) or Kannada (೦-೯), translate them or output verbatim; they will be normalized.
3. Clean all currency symbols (₹, Rs, INR). Output prices, quantities, and totals as numbers (floats).
4. Extract all line items individually in order with description, quantity, unit_price, and line_total.
5. If a field is missing, illegible, or not present, set its value to null.
"""

INVOICE_PROMPT = (
    SYSTEM_INSTRUCTION_BASE
    + """
Target JSON Schema:
{
  "vendor_name": "string or null",
  "invoice_date": "YYYY-MM-DD or string or null",
  "invoice_number": "string or null",
  "line_items": [
    {
      "description": "string",
      "quantity": float,
      "unit_price": float,
      "line_total": float
    }
  ],
  "subtotal": float or null,
  "tax_amount": float or null,
  "discount_amount": float or null,
  "grand_total": float or null
}
"""
)

PRESCRIPTION_PROMPT = (
    SYSTEM_INSTRUCTION_BASE
    + """
Target JSON Schema:
{
  "clinic_or_doctor_name": "string or null",
  "patient_name": "string or null",
  "document_date": "YYYY-MM-DD or string or null",
  "prescription_number": "string or null",
  "line_items": [
    {
      "description": "medication name & strength",
      "quantity": float,
      "dosage": "string (e.g. 1-0-1)",
      "duration": "string",
      "unit_price": float or null,
      "line_total": float or null
    }
  ],
  "subtotal": float or null,
  "tax_amount": float or null,
  "discount_amount": float or null,
  "grand_total": float or null
}
"""
)

KHATA_LEDGER_PROMPT = (
    SYSTEM_INSTRUCTION_BASE
    + """
Target JSON Schema:
{
  "customer_name": "string or null",
  "document_date": "YYYY-MM-DD or string or null",
  "account_number": "string or null",
  "previous_balance": float or null,
  "line_items": [
    {
      "description": "item/transaction description",
      "quantity": float,
      "unit_price": float,
      "line_total": float
    }
  ],
  "jama_credit": float or null,
  "naam_debit": float or null,
  "subtotal": float or null,
  "tax_amount": float or null,
  "discount_amount": float or null,
  "grand_total": float or null
}
"""
)

TIE_BREAKER_JUDGE_PROMPT = """You are an expert handwriting forensics judge.
Multiple vision extractors analyzed this document crop/image and produced conflicting candidate values for the field: "{field_name}".

Candidate values:
{candidates_json}

Task:
1. Examine the exact handwriting strokes and context in the document for this field.
2. Select the most accurate candidate value or transcribe the exact handwritten value yourself.
3. Provide your answer strictly as a single JSON object:
{
  "resolved_value": <resolved_value>,
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "brief note on stroke analysis"
}
"""


def get_prompt_for_doctype(doc_type: DocumentType) -> str:
    """Return appropriate extraction prompt based on document type."""
    if doc_type == DocumentType.PRESCRIPTION:
        return PRESCRIPTION_PROMPT
    elif doc_type == DocumentType.KHATA_LEDGER:
        return KHATA_LEDGER_PROMPT
    return INVOICE_PROMPT
