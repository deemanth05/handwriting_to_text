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
    CASH_BOOK = "CASH_BOOK"
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
    page_number: int = 1
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


class LedgerTransactionItem(BaseModel):
    """Standardized extracted cash book or khata ledger transaction entry."""

    row_id: int
    page_number: int = 1
    entry_date: ExtractedField[str] = Field(default_factory=lambda: ExtractedField[str](value=""))
    particulars: ExtractedField[str] = Field(default_factory=lambda: ExtractedField[str](value=""))
    voucher_no: ExtractedField[str] | None = None
    cash_out_debit: ExtractedField[float] = Field(
        default_factory=lambda: ExtractedField[float](value=0.0)
    )
    cash_in_credit: ExtractedField[float] = Field(
        default_factory=lambda: ExtractedField[float](value=0.0)
    )
    running_balance: ExtractedField[float] = Field(
        default_factory=lambda: ExtractedField[float](value=0.0)
    )
    balance_math_valid: bool = True
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
    page_count: int = 1
    pages: list[dict[str, Any]] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    status: str = Field(default="PROCESSED", description="PROCESSED | NEEDS_REVIEW | VERIFIED")
    math_validation: MathValidationResult = Field(default_factory=MathValidationResult)
    fields: dict[str, ExtractedField[Any]] = Field(default_factory=dict)
    line_items: list[LineItem] = Field(default_factory=list)
    ledger_items: list[LedgerTransactionItem] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    models_participated: list[str] = Field(default_factory=list)
    error_summary: str | None = None

    @model_validator(mode="after")
    def compute_review_status(self) -> "DocumentExtractionResponse":
        """Compute whether document must be routed to NEEDS_REVIEW queue."""
        if not self.math_validation.is_valid:
            self.status = "NEEDS_REVIEW"
            return self

        # When overall math is valid, mark as PROCESSED (straight-through processing)
        if self.math_validation.is_valid and (self.line_items or self.ledger_items):
            self.status = "PROCESSED"
            return self

        if self.overall_confidence < 0.85:
            self.status = "NEEDS_REVIEW"
            return self

        # Check individual fields that are present
        for field in self.fields.values():
            if field.value is not None and (field.needs_review or field.confidence < 0.75):
                self.status = "NEEDS_REVIEW"
                return self

        # Check line items
        for item in self.line_items:
            if item.needs_review or not item.row_math_valid:
                self.status = "NEEDS_REVIEW"
                return self

        # Check ledger items
        for l_item in self.ledger_items:
            if l_item.needs_review or not l_item.balance_math_valid:
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


def verify_ledger_math(
    items: list[LedgerTransactionItem],
    tolerance: float = 0.05,
) -> MathValidationResult:
    """Verify running balance arithmetic: Balance[t] = Balance[t-1] + In[t] - Out[t]."""
    errors: list[str] = []
    max_disc: float = 0.0

    if not items:
        return MathValidationResult(is_valid=True, discrepancy_amount=0.0, error_details=[])

    # Check if first row has opening credit / balance
    init_bal = items[0].running_balance.value
    init_in = items[0].cash_in_credit.value or 0.0
    init_out = items[0].cash_out_debit.value or 0.0
    if (init_bal is None or init_bal == 0.0) and (init_in > 0.0 or init_out > 0.0):
        prev_balance = round(init_in - init_out, 2)
        items[0].running_balance.value = prev_balance
    else:
        prev_balance = init_bal or 0.0

    items[0].balance_math_valid = True

    for i in range(1, len(items)):
        item = items[i]
        out_val = item.cash_out_debit.value or 0.0
        in_val = item.cash_in_credit.value or 0.0
        bal_val = item.running_balance.value

        if bal_val is None:
            continue

        expected_bal = round(prev_balance + in_val - out_val, 2)
        actual_bal = round(bal_val, 2)
        diff = round(abs(expected_bal - actual_bal), 2)

        if diff > tolerance:
            item.balance_math_valid = False
            item.needs_review = True
            desc = item.particulars.value or f"Row {item.row_id}"
            errors.append(
                f"Row {item.row_id} ({desc}): Expected balance {expected_bal:.2f} (prev {prev_balance:.2f} + in {in_val:.2f} - out {out_val:.2f}), got {actual_bal:.2f} (diff {diff:.2f})"
            )
            max_disc = max(max_disc, diff)
        else:
            item.balance_math_valid = True

        prev_balance = actual_bal

    return MathValidationResult(
        is_valid=(len(errors) == 0),
        discrepancy_amount=max_disc,
        error_details=errors,
    )

