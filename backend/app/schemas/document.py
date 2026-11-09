"""Pydantic v2 Canonical Schemas & Deterministic Math Validators.

Adheres strictly to the Paper-to-Structured-Data Engine SSOT.
LLMs are never trusted for arithmetic.
"""

from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class DocumentType(StrEnum):
    """Supported document categories."""

    INVOICE = "INVOICE"
    PRESCRIPTION = "PRESCRIPTION"
    KHATA_LEDGER = "KHATA_LEDGER"
    GENERAL = "GENERAL"


class ExtractedField(BaseModel, Generic[T]):
    """Standardized wrapped field contract with per-field confidence."""

    value: T | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    agreement: str = Field(default="0/3", description="Inter-model agreement ratio (e.g. 3/3, 2/3)")
    candidates: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw predictions from each model (e.g., {'model_a': ..., 'model_b': ...})",
    )
    needs_review: bool = False
    bounding_box: list[int] | None = Field(
        default=None, description="Optional [x_min, y_min, x_max, y_max] box"
    )


class LineItem(BaseModel):
    """Standardized extracted line item row."""

    row_id: int
    description: ExtractedField[str] = Field(default_factory=lambda: ExtractedField[str](value=""))
    quantity: ExtractedField[float] = Field(
        default_factory=lambda: ExtractedField[float](value=1.0)
    )
    unit_price: ExtractedField[float] = Field(
        default_factory=lambda: ExtractedField[float](value=0.0)
    )
    line_total: ExtractedField[float] = Field(
        default_factory=lambda: ExtractedField[float](value=0.0)
    )
    row_math_valid: bool = True
    needs_review: bool = False


class MathValidationResult(BaseModel):
    """Deterministic arithmetic validation output."""

    is_valid: bool = True
    discrepancy_amount: float = 0.0
    error_details: list[str] = Field(default_factory=list)


class DocumentExtractionResponse(BaseModel):
    """Canonical JSON output returned by API and reconciler."""

    document_id: str
    document_type: DocumentType
    overall_confidence: float = Field(ge=0.0, le=1.0)
    status: str = Field(default="PROCESSED", description="PROCESSED | NEEDS_REVIEW | VERIFIED")
    math_validation: MathValidationResult = Field(default_factory=MathValidationResult)
    fields: dict[str, ExtractedField[Any]] = Field(default_factory=dict)
    line_items: list[LineItem] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    models_participated: list[str] = Field(default_factory=list)
    error_summary: str | None = None

    @model_validator(mode="after")
    def compute_review_status(self) -> "DocumentExtractionResponse":
        """Compute whether document must be routed to NEEDS_REVIEW queue."""
        if not self.math_validation.is_valid:
            self.status = "NEEDS_REVIEW"
            return self

        if self.overall_confidence < 0.85:
            self.status = "NEEDS_REVIEW"
            return self

        # Check individual fields
        for field in self.fields.values():
            if field.needs_review or field.confidence < 0.75:
                self.status = "NEEDS_REVIEW"
                return self

        # Check line items
        for item in self.line_items:
            if item.needs_review or not item.row_math_valid:
                self.status = "NEEDS_REVIEW"
                return self

        return self


# Deterministic Math Verification Functions
def verify_row_math(
    quantity: float | None,
    unit_price: float | None,
    line_total: float | None,
    tolerance: float = 0.05,
) -> tuple[bool, float]:
    """Verify that quantity * unit_price == line_total within tolerance.

    Returns (is_valid, discrepancy).
    """
    if quantity is None or unit_price is None or line_total is None:
        return True, 0.0

    expected = round(quantity * unit_price, 2)
    actual = round(line_total, 2)
    discrepancy = round(abs(expected - actual), 2)
    is_valid = discrepancy <= tolerance
    return is_valid, discrepancy


def verify_document_math(
    subtotal: float | None,
    tax_amount: float | None,
    discount_amount: float | None,
    grand_total: float | None,
    line_totals: list[float],
    row_math_tolerance: float = 0.05,
    doc_math_tolerance: float = 0.50,
) -> MathValidationResult:
    """Verify line item sum matches subtotal and subtotal + tax - discount matches grand_total."""
    errors: list[str] = []
    max_discrepancy: float = 0.0

    tax = tax_amount or 0.0
    discount = discount_amount or 0.0

    # Rule 1: Sum of line items vs subtotal
    if line_totals and subtotal is not None and subtotal > 0:
        sum_lines = round(sum(line_totals), 2)
        diff_lines = round(abs(sum_lines - round(subtotal, 2)), 2)
        if diff_lines > doc_math_tolerance:
            errors.append(
                f"Sum of line items ({sum_lines:.2f}) does not match extracted Subtotal ({subtotal:.2f})."
            )
            max_discrepancy = max(max_discrepancy, diff_lines)

    # Rule 2: Subtotal + Tax - Discount vs Grand Total
    calc_base = subtotal if (subtotal is not None and subtotal > 0) else sum(line_totals)
    if grand_total is not None and (calc_base > 0 or line_totals):
        expected_grand = round(calc_base + tax - discount, 2)
        diff_grand = round(abs(expected_grand - round(grand_total, 2)), 2)
        if diff_grand > doc_math_tolerance:
            errors.append(
                f"Computed Grand Total ({expected_grand:.2f}) does not match extracted Grand Total ({grand_total:.2f})."
            )
            max_discrepancy = max(max_discrepancy, diff_grand)

    return MathValidationResult(
        is_valid=(len(errors) == 0),
        discrepancy_amount=max_discrepancy,
        error_details=errors,
    )
