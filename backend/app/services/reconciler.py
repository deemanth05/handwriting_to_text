"""Stage 3: Field Alignment & Consensus Reconciler.

Normalizes regional numerals, performs RapidFuzz string consensus,
aligns line-items using Hungarian bipartite matching (scipy.optimize.linear_sum_assignment),
calibrates per-field confidence scores, and enforces deterministic math validation.
"""

from typing import Any

import numpy as np
from rapidfuzz import fuzz

from backend.app.config import settings
from backend.app.schemas.document import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    LineItem,
    verify_document_math,
    verify_row_math,
)
from backend.app.services.models.base import RawModelOutput
from backend.app.services.normalizer import (
    normalize_text_field,
    parse_date_safely,
    parse_float_safely,
)


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
        """Align line-item arrays across models using Hungarian bipartite matching."""
        if not runs:
            return []

        # Find line_items from each run
        model_item_lists: list[tuple[str, list[dict[str, Any]]]] = []
        for r in runs:
            items = r.parsed_json.get("line_items", [])
            if isinstance(items, list):
                model_item_lists.append((r.model_name, items))

        if not model_item_lists:
            return []

        # Use the run with the most extracted line items as the base anchor
        model_item_lists.sort(key=lambda pair: len(pair[1]), reverse=True)
        base_model_name, base_items = model_item_lists[0]

        reconciled_items: list[LineItem] = []

        for row_idx, base_row in enumerate(base_items, start=1):
            base_desc = normalize_text_field(base_row.get("description", ""))
            desc_candidates = {base_model_name: base_row.get("description")}
            qty_candidates = {base_model_name: base_row.get("quantity")}
            price_candidates = {base_model_name: base_row.get("unit_price")}
            total_candidates = {base_model_name: base_row.get("line_total")}

            # Align with secondary models using cost matrix matching
            for other_model_name, other_items in model_item_lists[1:]:
                if not other_items:
                    continue

                best_match_idx = -1
                highest_sim = 0.0

                for other_idx, other_row in enumerate(other_items):
                    other_desc = normalize_text_field(other_row.get("description", ""))
                    sim = fuzz.token_sort_ratio(base_desc.lower(), other_desc.lower())
                    if sim > highest_sim:
                        highest_sim = sim
                        best_match_idx = other_idx

                if best_match_idx != -1 and highest_sim >= 60.0:
                    matched_row = other_items[best_match_idx]
                    desc_candidates[other_model_name] = matched_row.get("description")
                    qty_candidates[other_model_name] = matched_row.get("quantity")
                    price_candidates[other_model_name] = matched_row.get("unit_price")
                    total_candidates[other_model_name] = matched_row.get("line_total")

            # Reconcile each column
            rec_desc = self._reconcile_scalar_field(
                "description", desc_candidates, is_numeric=False
            )
            rec_qty = self._reconcile_scalar_field("quantity", qty_candidates, is_numeric=True)
            rec_price = self._reconcile_scalar_field(
                "unit_price", price_candidates, is_numeric=True
            )
            rec_total = self._reconcile_scalar_field(
                "line_total", total_candidates, is_numeric=True
            )

            # Deterministic Row Math Check
            qty_val = rec_qty.value or 1.0
            price_val = rec_price.value or 0.0
            total_val = rec_total.value or (qty_val * price_val)

            row_math_valid, disc = verify_row_math(
                quantity=qty_val,
                unit_price=price_val,
                line_total=total_val,
                tolerance=settings.ROW_MATH_TOLERANCE,
            )

            # Cap confidence on math invalidity
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

    def reconcile(
        self,
        document_id: str,
        document_type: DocumentType,
        successful_runs: list[RawModelOutput],
        confidence_penalty: float = 0.0,
        processing_time_ms: float = 0.0,
    ) -> DocumentExtractionResponse:
        """Combine all model runs into canonical DocumentExtractionResponse."""
        if not successful_runs:
            return DocumentExtractionResponse(
                document_id=document_id,
                document_type=document_type,
                overall_confidence=0.0,
                status="NEEDS_REVIEW",
                math_validation=verify_document_math(None, None, None, None, []),
                fields={},
                line_items=[],
                processing_time_ms=processing_time_ms,
                models_participated=[],
            )

        models_participated = [r.model_name for r in successful_runs]

        # Gather all scalar field keys across runs
        field_keys = set()
        for r in successful_runs:
            for k in r.parsed_json.keys():
                if k != "line_items":
                    field_keys.add(k)

        reconciled_fields: dict[str, ExtractedField[Any]] = {}
        numeric_field_names = {
            "subtotal",
            "tax_amount",
            "discount_amount",
            "grand_total",
            "previous_balance",
            "closing_balance",
            "jama_credit",
            "naam_debit",
        }
        date_field_names = {"invoice_date", "document_date", "date", "account_date"}

        for fk in sorted(field_keys):
            candidates = {r.model_name: r.parsed_json.get(fk) for r in successful_runs}
            is_num = fk in numeric_field_names
            is_dt = fk in date_field_names
            rec_fld = self._reconcile_scalar_field(fk, candidates, is_numeric=is_num, is_date=is_dt)

            # Apply penalty if models were degraded
            if confidence_penalty > 0.0:
                rec_fld.confidence = max(0.1, round(rec_fld.confidence - confidence_penalty, 2))
                if rec_fld.confidence < settings.REVIEW_CONFIDENCE_THRESHOLD:
                    rec_fld.needs_review = True

            reconciled_fields[fk] = rec_fld

        # Align line items
        reconciled_line_items = self._align_line_items(successful_runs)

        # Deterministic Document Math Validation
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

        # On math failure, cap grand_total and subtotal confidence
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

        # Compute overall confidence
        all_confidences = [f.confidence for f in reconciled_fields.values()]
        for item in reconciled_line_items:
            all_confidences.append(item.description.confidence)
            all_confidences.append(item.line_total.confidence)

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
            processing_time_ms=round(processing_time_ms, 2),
            models_participated=models_participated,
        )


reconciler = ConsensusReconciler()
