"""Stage 3: Field Alignment & Consensus Reconciler.

Normalizes regional numerals, performs RapidFuzz string consensus,
aligns line-items and ledger entries using true Kuhn-Munkres bipartite matching
(scipy.optimize.linear_sum_assignment), repairs visual OCR digit confusion deterministically,
and enforces strict arithmetic balance constraints.
"""

from typing import Any

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from backend.app.config import settings
from backend.app.schemas.document import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    LedgerTransactionItem,
    LineItem,
    MathValidationResult,
    verify_document_math,
    verify_ledger_math,
    verify_row_math,
)
from backend.app.services.models.base import RawModelOutput
from backend.app.services.normalizer import (
    normalize_text_field,
    parse_date_safely,
    parse_float_safely,
)

# Deterministic OCR Visual Confusion Mapping
CONFUSION_MAP: dict[str, list[str]] = {
    "0": ["8", "6", "9", "7"],
    "1": ["7", "4"],
    "2": ["7", "3"],
    "3": ["8", "5"],
    "4": ["1", "9"],
    "5": ["6", "3"],
    "6": ["5", "0", "8"],
    "7": ["1", "2", "0"],
    "8": ["3", "0", "6"],
    "9": ["4", "0"],
}


def get_digit_mutations(val: float) -> list[tuple[int, str, str, float]]:
    """Generate all candidate float values by single-digit substitution from visual confusion sets."""
    # Test both two-decimal string and integer representation (if integer)
    str_candidates = [f"{val:.2f}"]
    if val == int(val):
        str_candidates.append(str(int(val)))

    muts: list[tuple[int, str, str, float]] = []
    seen: set[float] = set()
    for s in str_candidates:
        for i, ch in enumerate(s):
            if ch in CONFUSION_MAP:
                for rep in CONFUSION_MAP[ch]:
                    cand_s = s[:i] + rep + s[i + 1 :]
                    try:
                        cand_v = round(float(cand_s), 2)
                        if cand_v not in seen:
                            seen.add(cand_v)
                            muts.append((i, ch, rep, cand_v))
                    except ValueError:
                        pass
    return muts


def repair_digit_confusion_row(
    q: float,
    p: float,
    t: float,
    tolerance: float = 0.05,
) -> tuple[float, float, float, bool]:
    """Auto-correct visual OCR confusion (e.g. 8 <-> 3, 1 <-> 7) if it satisfies Q * P == T."""
    if abs(round(q * p, 2) - round(t, 2)) <= tolerance:
        return q, p, t, False

    # 1. Missing field arithmetic recovery (when 2 of 3 fields are non-zero)
    if p == 0.0 and q > 0.0 and t > 0.0:
        recovered_p = round(t / q, 2)
        return q, recovered_p, t, True
    if t == 0.0 and q > 0.0 and p > 0.0:
        recovered_t = round(q * p, 2)
        return q, p, recovered_t, True
    if q == 0.0 and p > 0.0 and t > 0.0:
        recovered_q = round(t / p, 2)
        return recovered_q, p, t, True

    # 2. Try mutating P (most common OCR error in unit prices)
    for _, _, _, cand_p in get_digit_mutations(p):
        if cand_p > 0 and abs(round(q * cand_p, 2) - round(t, 2)) <= tolerance:
            return q, cand_p, t, True

    # 3. Try mutating T
    for _, _, _, cand_t in get_digit_mutations(t):
        if cand_t > 0 and abs(round(q * p, 2) - round(cand_t, 2)) <= tolerance:
            return q, p, cand_t, True

    # 4. Try mutating Q
    for _, _, _, cand_q in get_digit_mutations(q):
        if cand_q > 0 and abs(round(cand_q * p, 2) - round(t, 2)) <= tolerance:
            return cand_q, p, t, True

    return q, p, t, False


def repair_ledger_balance_row(
    prev_balance: float,
    out_val: float,
    in_val: float,
    bal_val: float,
    tolerance: float = 0.05,
) -> tuple[float, float, float, bool]:
    """Auto-correct ledger balance equation: Balance[t] = Balance[t-1] + In[t] - Out[t]."""
    expected = round(prev_balance + in_val - out_val, 2)
    if abs(expected - round(bal_val, 2)) <= tolerance:
        return out_val, in_val, bal_val, False

    # 1. Recover smudged/missing running balance when out or in is known
    if bal_val == 0.0 and (out_val > 0.0 or in_val > 0.0):
        recovered_bal = round(prev_balance + in_val - out_val, 2)
        if recovered_bal >= 0.0:
            return out_val, in_val, recovered_bal, True

    # 2. Recover smudged/missing Out or In when a valid non-zero balance is known
    if out_val == 0.0 and in_val == 0.0 and bal_val > 0.0 and abs(prev_balance - bal_val) > tolerance:
        if prev_balance > bal_val:
            return round(prev_balance - bal_val, 2), in_val, bal_val, True
        else:
            return out_val, round(bal_val - prev_balance, 2), bal_val, True

    # 3. Digit confusion repair on out_val
    for _, _, _, cand_out in get_digit_mutations(out_val):
        if abs(round(prev_balance + in_val - cand_out, 2) - round(bal_val, 2)) <= tolerance:
            return cand_out, in_val, bal_val, True

    # 4. Digit confusion repair on bal_val
    for _, _, _, cand_bal in get_digit_mutations(bal_val):
        if abs(expected - round(cand_bal, 2)) <= tolerance:
            return out_val, in_val, cand_bal, True

    # 5. Digit confusion repair on in_val
    for _, _, _, cand_in in get_digit_mutations(in_val):
        if abs(round(prev_balance + cand_in - out_val, 2) - round(bal_val, 2)) <= tolerance:
            return out_val, cand_in, bal_val, True

    return out_val, in_val, bal_val, False


class ConsensusReconciler:
    """Ensemble reconciler that combines multiple raw model extractions."""

    def __init__(self):
        self.string_sim_threshold = 88.0

    def _reconcile_scalar_field(
        self,
        field_name: str,
        candidates: dict[str, Any],
        is_numeric: bool = False,
        is_date: bool = False,
    ) -> ExtractedField[Any]:
        """Align scalar field across candidate outputs."""
        if not candidates:
            return ExtractedField(
                value=None,
                confidence=0.0,
                agreement="0/3",
                candidates={},
                needs_review=True,
            )

        # Normalize candidates
        normalized_cands: dict[str, Any] = {}
        for model_k, val in candidates.items():
            if val is None:
                normalized_cands[model_k] = None
            elif is_numeric:
                normalized_cands[model_k] = parse_float_safely(val)
            elif is_date:
                normalized_cands[model_k] = parse_date_safely(val)
            else:
                normalized_cands[model_k] = normalize_text_field(val)

        valid_vals = [v for v in normalized_cands.values() if v is not None and v != ""]
        total_models = max(len(candidates), 3)

        if not valid_vals:
            return ExtractedField(
                value=None,
                confidence=0.0,
                agreement=f"0/{total_models}",
                candidates=candidates,
                needs_review=True,
            )

        # Count agreements
        agreement_groups: list[list[str]] = []
        for model_name, val in normalized_cands.items():
            if val is None or val == "":
                continue
            matched = False
            for group in agreement_groups:
                lead_model = group[0]
                lead_val = normalized_cands[lead_model]

                if is_numeric:
                    if abs(float(val) - float(lead_val)) <= 0.05:
                        group.append(model_name)
                        matched = True
                        break
                elif is_date:
                    if str(val) == str(lead_val):
                        group.append(model_name)
                        matched = True
                        break
                else:
                    ratio = fuzz.token_sort_ratio(str(val).lower(), str(lead_val).lower())
                    if ratio >= self.string_sim_threshold:
                        group.append(model_name)
                        matched = True
                        break
            if not matched:
                agreement_groups.append([model_name])

        # Sort groups by size descending
        agreement_groups.sort(key=len, reverse=True)
        largest_group = agreement_groups[0]
        chosen_val = normalized_cands[largest_group[0]]
        agree_count = len(largest_group)
        agreement_str = f"{agree_count}/{total_models}"

        # Confidence calibration
        if agree_count >= 3:
            conf = settings.CONFIDENCE_3_OF_3
        elif agree_count == 2:
            conf = settings.CONFIDENCE_2_OF_3_VALID
        else:
            conf = settings.CONFIDENCE_DISAGREEMENT

        needs_review = conf < settings.REVIEW_CONFIDENCE_THRESHOLD

        return ExtractedField(
            value=chosen_val,
            confidence=conf,
            agreement=agreement_str,
            candidates=candidates,
            needs_review=needs_review,
        )

    def _align_line_items(
        self,
        runs: list[RawModelOutput],
    ) -> list[LineItem]:
        """Align line-item arrays across models using Kuhn-Munkres bipartite matching."""
        if not runs:
            return []

        # Find line_items from each run
        model_item_lists: list[tuple[str, list[dict[str, Any]]]] = []
        for r in runs:
            items = r.parsed_json.get("line_items", [])
            if isinstance(items, list) and len(items) > 0:
                model_item_lists.append((r.model_name, items))

        if not model_item_lists:
            return []

        # Use the run with the most extracted line items as the base anchor
        model_item_lists.sort(key=lambda pair: len(pair[1]), reverse=True)
        base_model_name, base_items = model_item_lists[0]

        # Map: (other_model_name, base_idx) -> other_item_dict
        aligned_pairs: dict[tuple[str, int], dict[str, Any]] = {}
        for other_model_name, other_items in model_item_lists[1:]:
            if not other_items:
                continue
            N = len(base_items)
            M = len(other_items)
            cost_matrix = np.zeros((N, M))
            for i, b_item in enumerate(base_items):
                b_desc = normalize_text_field(b_item.get("description", "")).lower()
                b_tot = parse_float_safely(b_item.get("line_total")) or 0.0
                for j, o_item in enumerate(other_items):
                    o_desc = normalize_text_field(o_item.get("description", "")).lower()
                    o_tot = parse_float_safely(o_item.get("line_total")) or 0.0

                    if not b_desc and not o_desc:
                        price_diff = abs(b_tot - o_tot)
                        sim = 90.0 if (b_tot > 0 and price_diff <= 0.05) else max(10.0, 50.0 - abs(i - j) * 5.0)
                    else:
                        sim = float(fuzz.token_sort_ratio(b_desc, o_desc))
                    cost_matrix[i, j] = 100.0 - max(0.0, sim)

            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            for r, c in zip(row_ind, col_ind):
                if 100.0 - cost_matrix[r, c] >= 50.0:
                    aligned_pairs[(other_model_name, r)] = other_items[c]

        reconciled_items: list[LineItem] = []

        for row_idx, base_row in enumerate(base_items, start=1):
            base_idx = row_idx - 1
            desc_candidates = {base_model_name: base_row.get("description")}
            qty_candidates = {base_model_name: base_row.get("quantity")}
            price_candidates = {base_model_name: base_row.get("unit_price")}
            total_candidates = {base_model_name: base_row.get("line_total")}

            for other_model_name, _ in model_item_lists[1:]:
                if (other_model_name, base_idx) in aligned_pairs:
                    matched_row = aligned_pairs[(other_model_name, base_idx)]
                    desc_candidates[other_model_name] = matched_row.get("description")
                    qty_candidates[other_model_name] = matched_row.get("quantity")
                    price_candidates[other_model_name] = matched_row.get("unit_price")
                    total_candidates[other_model_name] = matched_row.get("line_total")

            # Reconcile each column
            rec_desc = self._reconcile_scalar_field("description", desc_candidates, is_numeric=False)
            rec_qty = self._reconcile_scalar_field("quantity", qty_candidates, is_numeric=True)
            rec_price = self._reconcile_scalar_field("unit_price", price_candidates, is_numeric=True)
            rec_total = self._reconcile_scalar_field("line_total", total_candidates, is_numeric=True)

            qty_val = rec_qty.value or 1.0
            price_val = rec_price.value or 0.0
            total_val = rec_total.value or round(qty_val * price_val, 2)

            # Deterministic Digit Confusion Repair
            q_rep, p_rep, t_rep, was_repaired = repair_digit_confusion_row(
                q=qty_val,
                p=price_val,
                t=total_val,
                tolerance=settings.ROW_MATH_TOLERANCE,
            )
            if was_repaired:
                rec_qty.value = q_rep
                rec_price.value = p_rep
                rec_total.value = t_rep
                qty_val, price_val, total_val = q_rep, p_rep, t_rep
                rec_total.confidence = 0.95
                rec_total.needs_review = False

            row_math_valid, _ = verify_row_math(
                quantity=qty_val,
                unit_price=price_val,
                line_total=total_val,
                tolerance=settings.ROW_MATH_TOLERANCE,
            )

            if not row_math_valid:
                rec_total.confidence = min(rec_total.confidence, 0.45)
                rec_total.needs_review = True

            needs_review = (
                not row_math_valid
                or rec_desc.needs_review
                or rec_qty.needs_review
                or rec_price.needs_review
                or rec_total.needs_review
            )

            reconciled_items.append(
                LineItem(
                    row_id=row_idx,
                    description=rec_desc,
                    quantity=rec_qty,
                    unit_price=rec_price,
                    line_total=rec_total,
                    row_math_valid=row_math_valid,
                    needs_review=needs_review,
                )
            )

        return reconciled_items

    def _align_ledger_items(
        self,
        runs: list[RawModelOutput],
    ) -> list[LedgerTransactionItem]:
        """Align ledger entries across models using Kuhn-Munkres bipartite matching and balance solver."""
        if not runs:
            return []

        model_ledger_lists: list[tuple[str, list[dict[str, Any]]]] = []
        for r in runs:
            items = r.parsed_json.get("ledger_items", [])
            if isinstance(items, list) and len(items) > 0:
                model_ledger_lists.append((r.model_name, items))

        if not model_ledger_lists:
            return []

        model_ledger_lists.sort(key=lambda pair: len(pair[1]), reverse=True)
        base_model_name, base_items = model_ledger_lists[0]

        aligned_pairs: dict[tuple[str, int], dict[str, Any]] = {}
        for other_model_name, other_items in model_ledger_lists[1:]:
            if not other_items:
                continue
            N = len(base_items)
            M = len(other_items)
            cost_matrix = np.zeros((N, M))
            for i, b_item in enumerate(base_items):
                b_part = normalize_text_field(b_item.get("particulars", "")).lower()
                b_bal = parse_float_safely(b_item.get("running_balance")) or 0.0
                for j, o_item in enumerate(other_items):
                    o_part = normalize_text_field(o_item.get("particulars", "")).lower()
                    o_bal = parse_float_safely(o_item.get("running_balance")) or 0.0

                    if not b_part and not o_part:
                        bal_diff = abs(b_bal - o_bal)
                        sim = 90.0 if (b_bal > 0 and bal_diff <= 0.05) else max(10.0, 50.0 - abs(i - j) * 5.0)
                    else:
                        sim = float(fuzz.token_sort_ratio(b_part, o_part))
                    cost_matrix[i, j] = 100.0 - max(0.0, sim)

            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            for r, c in zip(row_ind, col_ind):
                if 100.0 - cost_matrix[r, c] >= 50.0:
                    aligned_pairs[(other_model_name, r)] = other_items[c]

        reconciled_ledger: list[LedgerTransactionItem] = []

        for row_idx, base_row in enumerate(base_items, start=1):
            base_idx = row_idx - 1
            date_cands = {base_model_name: base_row.get("entry_date")}
            part_cands = {base_model_name: base_row.get("particulars")}
            voucher_cands = {base_model_name: base_row.get("voucher_no")}
            out_cands = {base_model_name: base_row.get("cash_out_debit")}
            in_cands = {base_model_name: base_row.get("cash_in_credit")}
            bal_cands = {base_model_name: base_row.get("running_balance")}

            for other_model_name, _ in model_ledger_lists[1:]:
                if (other_model_name, base_idx) in aligned_pairs:
                    matched_row = aligned_pairs[(other_model_name, base_idx)]
                    date_cands[other_model_name] = matched_row.get("entry_date")
                    part_cands[other_model_name] = matched_row.get("particulars")
                    voucher_cands[other_model_name] = matched_row.get("voucher_no")
                    out_cands[other_model_name] = matched_row.get("cash_out_debit")
                    in_cands[other_model_name] = matched_row.get("cash_in_credit")
                    bal_cands[other_model_name] = matched_row.get("running_balance")

            rec_date = self._reconcile_scalar_field("entry_date", date_cands, is_date=True)
            rec_part = self._reconcile_scalar_field("particulars", part_cands, is_numeric=False)
            rec_voucher = (
                self._reconcile_scalar_field("voucher_no", voucher_cands, is_numeric=False)
                if any(v is not None for v in voucher_cands.values())
                else None
            )
            rec_out = self._reconcile_scalar_field("cash_out_debit", out_cands, is_numeric=True)
            rec_in = self._reconcile_scalar_field("cash_in_credit", in_cands, is_numeric=True)
            rec_bal = self._reconcile_scalar_field("running_balance", bal_cands, is_numeric=True)

            reconciled_ledger.append(
                LedgerTransactionItem(
                    row_id=row_idx,
                    entry_date=rec_date,
                    particulars=rec_part,
                    voucher_no=rec_voucher.value if rec_voucher else None,
                    cash_out_debit=rec_out,
                    cash_in_credit=rec_in,
                    running_balance=rec_bal,
                    balance_math_valid=True,
                    needs_review=rec_part.needs_review or rec_bal.needs_review,
                )
            )

        # Sequential Running Balance Repair & Constraint Solver
        if reconciled_ledger:
            prev_balance = reconciled_ledger[0].running_balance.value or 0.0
            reconciled_ledger[0].balance_math_valid = True

            for t in range(1, len(reconciled_ledger)):
                item = reconciled_ledger[t]
                out_val = item.cash_out_debit.value or 0.0
                in_val = item.cash_in_credit.value or 0.0
                bal_val = item.running_balance.value or 0.0

                o_rep, i_rep, b_rep, was_repaired = repair_ledger_balance_row(
                    prev_balance=prev_balance,
                    out_val=out_val,
                    in_val=in_val,
                    bal_val=bal_val,
                    tolerance=settings.ROW_MATH_TOLERANCE,
                )

                if was_repaired:
                    item.cash_out_debit.value = o_rep
                    item.cash_in_credit.value = i_rep
                    item.running_balance.value = b_rep
                    item.running_balance.confidence = 0.95
                    item.balance_math_valid = True
                    item.needs_review = False
                    prev_balance = b_rep
                else:
                    expected = round(prev_balance + in_val - out_val, 2)
                    is_valid = abs(expected - round(bal_val, 2)) <= settings.ROW_MATH_TOLERANCE
                    item.balance_math_valid = is_valid
                    if not is_valid:
                        item.running_balance.confidence = min(item.running_balance.confidence, 0.45)
                        item.needs_review = True
                    prev_balance = bal_val

        return reconciled_ledger

    def reconcile(
        self,
        document_id: str,
        document_type: DocumentType,
        successful_runs: list[RawModelOutput],
        failed_runs: list[RawModelOutput] | None = None,
        confidence_penalty: float = 0.0,
        processing_time_ms: float = 0.0,
    ) -> DocumentExtractionResponse:
        """Combine all model runs into canonical DocumentExtractionResponse."""
        if not successful_runs:
            err_msg: str | None = None
            if failed_runs:
                unique_errs = [r.error for r in failed_runs if r.error]
                if unique_errs:
                    err_msg = "; ".join(unique_errs[:2])
            return DocumentExtractionResponse(
                document_id=document_id,
                document_type=document_type,
                overall_confidence=0.0,
                status="NEEDS_REVIEW",
                math_validation=verify_document_math(None, None, None, None, []),
                fields={},
                line_items=[],
                ledger_items=[],
                processing_time_ms=processing_time_ms,
                models_participated=[],
                error_summary=err_msg,
            )

        models_participated = [r.model_name for r in successful_runs]

        # Gather all scalar field keys across runs
        field_keys = set()
        for r in successful_runs:
            for k in r.parsed_json.keys():
                if k not in ("line_items", "ledger_items"):
                    field_keys.add(k)

        reconciled_fields: dict[str, ExtractedField[Any]] = {}
        numeric_field_names = {
            "subtotal",
            "tax_amount",
            "discount_amount",
            "grand_total",
            "previous_balance",
            "closing_balance",
            "opening_balance",
            "jama_credit",
            "naam_debit",
        }
        date_field_names = {"invoice_date", "document_date", "date", "account_date"}

        for fk in sorted(field_keys):
            candidates = {r.model_name: r.parsed_json.get(fk) for r in successful_runs}
            is_num = fk in numeric_field_names
            is_dt = fk in date_field_names
            rec_fld = self._reconcile_scalar_field(fk, candidates, is_numeric=is_num, is_date=is_dt)

            if confidence_penalty > 0.0:
                rec_fld.confidence = max(0.1, round(rec_fld.confidence - confidence_penalty, 2))
                if rec_fld.confidence < settings.REVIEW_CONFIDENCE_THRESHOLD:
                    rec_fld.needs_review = True

            reconciled_fields[fk] = rec_fld

        # Align tables based on document type
        reconciled_line_items = self._align_line_items(successful_runs)
        reconciled_ledger_items = self._align_ledger_items(successful_runs)

        # Deterministic Math Auditing
        if reconciled_ledger_items:
            math_result = verify_ledger_math(
                items=reconciled_ledger_items,
                tolerance=settings.ROW_MATH_TOLERANCE,
            )
        else:
            subtotal_val = reconciled_fields.get("subtotal", ExtractedField()).value
            tax_val = reconciled_fields.get("tax_amount", ExtractedField()).value
            disc_val = reconciled_fields.get("discount_amount", ExtractedField()).value
            grand_val = reconciled_fields.get("grand_total", ExtractedField()).value

            line_totals = [
                item.line_total.value
                for item in reconciled_line_items
                if item.line_total.value is not None
            ]

            math_result = verify_document_math(
                subtotal=subtotal_val,
                tax_amount=tax_val,
                discount_amount=disc_val,
                grand_total=grand_val,
                line_totals=line_totals,
                doc_math_tolerance=settings.DOC_MATH_TOLERANCE,
            )

            if not math_result.is_valid:
                if "grand_total" in reconciled_fields:
                    reconciled_fields["grand_total"].confidence = min(
                        reconciled_fields["grand_total"].confidence, 0.45
                    )
                    reconciled_fields["grand_total"].needs_review = True
                if "subtotal" in reconciled_fields:
                    reconciled_fields["subtotal"].confidence = min(
                        reconciled_fields["subtotal"].confidence, 0.45
                    )
                    reconciled_fields["subtotal"].needs_review = True

        # Overall Confidence
        all_confidences = [f.confidence for f in reconciled_fields.values()]
        for item in reconciled_line_items:
            all_confidences.append(item.description.confidence)
            all_confidences.append(item.line_total.confidence)
        for l_item in reconciled_ledger_items:
            all_confidences.append(l_item.particulars.confidence)
            all_confidences.append(l_item.running_balance.confidence)

        if all_confidences:
            mean_conf = float(np.mean(all_confidences))
            if not math_result.is_valid:
                mean_conf = min(mean_conf, 0.55)
            overall_conf = round(mean_conf, 2)
        else:
            overall_conf = 0.0

        return DocumentExtractionResponse(
            document_id=document_id,
            document_type=document_type,
            overall_confidence=overall_conf,
            math_validation=math_result,
            fields=reconciled_fields,
            line_items=reconciled_line_items,
            ledger_items=reconciled_ledger_items,
            processing_time_ms=round(processing_time_ms, 2),
            models_participated=models_participated,
        )


reconciler = ConsensusReconciler()
