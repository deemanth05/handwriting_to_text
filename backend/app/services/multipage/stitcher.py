"""Multi-Page Cross-Table Stitching & Ledger Continuity Service.

Stitches independently extracted document pages into a single cohesive,
arithmetically validated DocumentExtractionResponse:
1. Header & Scalar Metadata Inheritance (pulling vendor, bill no, GSTIN from primary header pages)
2. Table Continuation Stitching with C/F (Carried Forward) and B/F (Brought Forward) filtering
3. Cross-Page Ledger Running-Balance Invariant Validation (Closing_N == Opening_{N+1})
4. Global Multi-Page Deterministic Arithmetic Verification
"""

from __future__ import annotations

import re
from typing import Any

from backend.app.schemas.document import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    LedgerTransactionItem,
    LineItem,
    MathValidationResult,
)

# Regex to detect transitional subtotal rows that should not count as billed inventory items
TRANSITIONAL_ROW_PATTERN = re.compile(
    r"\b(c/f|carried\s+forward|b/f|brought\s+forward|b/d|brought\s+down|c/o|balance\s+b/f|balance\s+c/f|total\s+c/f|total\s+b/f|page\s+total)\b",
    re.IGNORECASE,
)


class MultiPageStitcher:
    """Stitches page-by-page extractions into a unified multi-page document."""

    def stitch(
        self,
        document_id: str,
        document_type: DocumentType,
        page_responses: list[DocumentExtractionResponse],
    ) -> DocumentExtractionResponse:
        """Main dispatcher for stitching multi-page responses."""
        if not page_responses:
            raise ValueError("Cannot stitch empty list of page responses.")

        if len(page_responses) == 1:
            # Single-page pass-through with page metadata enriched
            single = page_responses[0]
            single.page_count = 1
            for item in single.line_items:
                item.page_number = 1
            for l_item in single.ledger_items:
                l_item.page_number = 1
            single.pages = [
                {
                    "page_number": 1,
                    "confidence": single.overall_confidence,
                    "items_count": len(single.line_items) or len(single.ledger_items),
                    "math_valid": single.math_validation.is_valid,
                }
            ]
            return single

        if document_type in {DocumentType.CASH_BOOK, DocumentType.KHATA_LEDGER}:
            return self._stitch_ledger_pages(document_id, document_type, page_responses)
        else:
            return self._stitch_invoice_pages(document_id, document_type, page_responses)

    def _stitch_invoice_pages(
        self,
        document_id: str,
        document_type: DocumentType,
        pages: list[DocumentExtractionResponse],
    ) -> DocumentExtractionResponse:
        """Stitch multiple invoice pages into a single itemized register."""
        # 1. Consolidate scalar fields (vendor, invoice_number, date, gstin, etc.)
        # Pages earlier in the document (Page 1) usually have the true legal header.
        consolidated_fields: dict[str, ExtractedField[Any]] = {}

        # Collect all unique field keys across all pages
        all_keys: set[str] = set()
        for p in pages:
            all_keys.update(p.fields.keys())

        # Specific fields that typically live on the final summary page
        summary_field_keys = {
            "subtotal", "tax_amount", "discount_amount", "grand_total",
            "cgst_amount", "sgst_amount", "igst_amount", "round_off"
        }

        for key in all_keys:
            best_field: ExtractedField[Any] | None = None
            best_score: float = -1.0

            for p_idx, p in enumerate(pages, 1):
                f = p.fields.get(key)
                if f and f.value not in (None, "", 0.0):
                    score = f.confidence
                    # Prioritize first page for headers, last page for totals
                    if key in summary_field_keys and p_idx == len(pages):
                        score += 0.25
                    elif key not in summary_field_keys and p_idx == 1:
                        score += 0.25

                    if score > best_score:
                        best_score = score
                        best_field = f

            if best_field:
                consolidated_fields[key] = best_field

        # 2. Table Continuation: Concatenate line items and filter out C/F and B/F rows
        stitched_items: list[LineItem] = []
        global_row_id = 1
        page_summaries: list[dict[str, Any]] = []

        for p_idx, p in enumerate(pages, 1):
            items_this_page = 0
            for item in p.line_items:
                desc = str(item.description.value or "")

                # Exclude transitional Carried Forward / Brought Forward rows
                if TRANSITIONAL_ROW_PATTERN.search(desc):
                    continue

                stitched_item = LineItem(
                    row_id=global_row_id,
                    page_number=p_idx,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                    row_math_valid=item.row_math_valid,
                    needs_review=item.needs_review,
                )
                stitched_items.append(stitched_item)
                global_row_id += 1
                items_this_page += 1

            page_summaries.append({
                "page_number": p_idx,
                "confidence": p.overall_confidence,
                "items_count": items_this_page,
                "math_valid": p.math_validation.is_valid,
            })

        # 3. Global Multi-Page Arithmetic Audit
        computed_items_sum = round(
            sum(float(it.line_total.value or 0.0) for it in stitched_items), 2
        )

        subtotal_val = float(consolidated_fields.get("subtotal", ExtractedField(value=0.0)).value or 0.0)
        tax_val = float(consolidated_fields.get("tax_amount", ExtractedField(value=0.0)).value or 0.0)
        discount_val = float(consolidated_fields.get("discount_amount", ExtractedField(value=0.0)).value or 0.0)
        grand_total_val = float(consolidated_fields.get("grand_total", ExtractedField(value=0.0)).value or 0.0)

        error_details: list[str] = []
        is_math_valid = True
        discrepancy = 0.0

        if subtotal_val > 0:
            if abs(computed_items_sum - subtotal_val) > 0.05:
                is_math_valid = False
                discrepancy = round(abs(computed_items_sum - subtotal_val), 2)
                error_details.append(
                    f"Cross-page line items sum (₹{computed_items_sum:,.2f}) does not match invoice subtotal (₹{subtotal_val:,.2f}). Variance: ₹{discrepancy:,.2f}"
                )
        elif not subtotal_val and computed_items_sum > 0:
            # Auto-populate missing subtotal from verified stitched sum
            subtotal_val = computed_items_sum
            consolidated_fields["subtotal"] = ExtractedField(
                value=subtotal_val,
                confidence=0.95,
                sources=["MULTI_PAGE_STITCHER"],
            )

        if grand_total_val > 0:
            expected_grand = round(subtotal_val + tax_val - discount_val, 2)
            if abs(expected_grand - grand_total_val) > 0.05:
                is_math_valid = False
                disc = round(abs(expected_grand - grand_total_val), 2)
                discrepancy = max(discrepancy, disc)
                error_details.append(
                    f"Grand total (₹{grand_total_val:,.2f}) != Subtotal + Tax - Discount (₹{expected_grand:,.2f}). Variance: ₹{disc:,.2f}"
                )
        elif subtotal_val > 0:
            grand_total_val = round(subtotal_val + tax_val - discount_val, 2)
            consolidated_fields["grand_total"] = ExtractedField(
                value=grand_total_val,
                confidence=0.95,
                sources=["MULTI_PAGE_STITCHER"],
            )

        # 4. Synthesize overall confidence and model participation
        avg_confidence = round(sum(p.overall_confidence for p in pages) / len(pages), 3)
        all_models = sorted(list({m for p in pages for m in p.models_participated}))
        total_time_ms = round(sum(p.processing_time_ms for p in pages), 1)

        return DocumentExtractionResponse(
            document_id=document_id,
            document_type=document_type,
            page_count=len(pages),
            pages=page_summaries,
            overall_confidence=avg_confidence,
            fields=consolidated_fields,
            line_items=stitched_items,
            ledger_items=[],
            math_validation=MathValidationResult(
                is_valid=is_math_valid,
                discrepancy_amount=discrepancy,
                error_details=error_details,
            ),
            processing_time_ms=total_time_ms,
            models_participated=all_models,
        )

    def _stitch_ledger_pages(
        self,
        document_id: str,
        document_type: DocumentType,
        pages: list[DocumentExtractionResponse],
    ) -> DocumentExtractionResponse:
        """Stitch multiple cash book / khata pages with cross-page balance continuity enforcement."""
        # 1. Consolidate metadata (book title, account holder name, etc.)
        consolidated_fields: dict[str, ExtractedField[Any]] = {}
        for p in pages:
            for k, f in p.fields.items():
                if f and f.value not in (None, ""):
                    if k not in consolidated_fields or f.confidence > consolidated_fields[k].confidence:
                        consolidated_fields[k] = f

        # 2. Sequential ledger transaction concatenation
        stitched_ledger: list[LedgerTransactionItem] = []
        global_row_id = 1
        page_summaries: list[dict[str, Any]] = []

        for p_idx, p in enumerate(pages, 1):
            items_this_page = 0
            for it in p.ledger_items:
                part = str(it.particulars.value or "")
                # Skip standalone B/F or C/F lines if they duplicate opening/closing balance
                if TRANSITIONAL_ROW_PATTERN.search(part) and (it.cash_out_debit.value == 0 and it.cash_in_credit.value == 0):
                    continue

                stitched_item = LedgerTransactionItem(
                    row_id=global_row_id,
                    page_number=p_idx,
                    entry_date=it.entry_date,
                    particulars=it.particulars,
                    voucher_no=it.voucher_no,
                    cash_out_debit=it.cash_out_debit,
                    cash_in_credit=it.cash_in_credit,
                    running_balance=it.running_balance,
                    balance_math_valid=it.balance_math_valid,
                    needs_review=it.needs_review,
                )
                stitched_ledger.append(stitched_item)
                global_row_id += 1
                items_this_page += 1

            page_summaries.append({
                "page_number": p_idx,
                "confidence": p.overall_confidence,
                "items_count": items_this_page,
                "math_valid": p.math_validation.is_valid,
            })

        # 3. Cross-Page Balance Continuity Check
        # Page N's closing balance must match Page N+1's opening balance
        error_details: list[str] = []
        is_math_valid = True
        discrepancy = 0.0

        for i in range(len(pages) - 1):
            curr_p = pages[i]
            next_p = pages[i + 1]

            # Get Page N's last running balance
            curr_last_bal = None
            if curr_p.ledger_items:
                curr_last_bal = float(curr_p.ledger_items[-1].running_balance.value or 0.0)

            # Get Page N+1's first running balance
            next_first_item = next_p.ledger_items[0] if next_p.ledger_items else None

            if curr_last_bal is not None and next_first_item:
                next_in = float(next_first_item.cash_in_credit.value or 0.0)
                next_out = float(next_first_item.cash_out_debit.value or 0.0)
                next_first_bal = float(next_first_item.running_balance.value or 0.0)

                # Expected balance after first entry of Page N+1
                expected_first_bal = round(curr_last_bal + next_in - next_out, 2)
                if abs(expected_first_bal - next_first_bal) > 0.05:
                    is_math_valid = False
                    diff = round(abs(expected_first_bal - next_first_bal), 2)
                    discrepancy = max(discrepancy, diff)
                    error_details.append(
                        f"Cross-page ledger continuity break between Page {i+1} and Page {i+2}: "
                        f"Page {i+1} closed at ₹{curr_last_bal:,.2f}, but Page {i+2} first entry resulted in "
                        f"₹{next_first_bal:,.2f} instead of expected ₹{expected_first_bal:,.2f}. Variance: ₹{diff:,.2f}"
                    )

        # Record opening and closing balance on consolidated fields
        if stitched_ledger:
            consolidated_fields["closing_balance"] = ExtractedField(
                value=stitched_ledger[-1].running_balance.value,
                confidence=0.95,
                sources=["MULTI_PAGE_STITCHER"],
            )

        avg_confidence = round(sum(p.overall_confidence for p in pages) / len(pages), 3)
        all_models = sorted(list({m for p in pages for m in p.models_participated}))
        total_time_ms = round(sum(p.processing_time_ms for p in pages), 1)

        return DocumentExtractionResponse(
            document_id=document_id,
            document_type=document_type,
            page_count=len(pages),
            pages=page_summaries,
            overall_confidence=avg_confidence,
            fields=consolidated_fields,
            line_items=[],
            ledger_items=stitched_ledger,
            math_validation=MathValidationResult(
                is_valid=is_math_valid,
                discrepancy_amount=discrepancy,
                error_details=error_details,
            ),
            processing_time_ms=total_time_ms,
            models_participated=all_models,
        )
