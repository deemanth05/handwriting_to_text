"""Bilateral Block Splitter for Document Summary and Footer Disambiguation.

Splits the summary/footer zone along a horizontal mid-gutter so that left-hand
narratives (terms & conditions, amount in words, bank details) and right-hand
totals (subtotal, CGST, SGST, discount, round-off, grand total) do not merge into false table rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def parse_numeric(text: str) -> float:
    """Parse string to float, normalizing punctuation quirks like 23:60 -> 23.60, commas, currency symbols."""
    if not text:
        return 0.0
    cleaned = text.strip()
    is_negative = cleaned.startswith("-") or ("(" in cleaned and ")" in cleaned and "cr" not in cleaned.lower())
    cleaned = re.sub(r"[₹$£€]|rs\.?|inr", "", cleaned, flags=re.IGNORECASE).strip()
    # Replace colon or semicolon between digits with dot (e.g. 23:60 -> 23.60)
    cleaned = re.sub(r"(?<=\d)[:;](?=\d)", ".", cleaned)
    # Thousand separators
    if re.search(r"\d+,\d{3}", cleaned):
        cleaned = cleaned.replace(",", "")
    else:
        # Decimal comma (e.g. 23,60 -> 23.60)
        cleaned = re.sub(r"(?<=\d),(?=\d{1,2}$)", ".", cleaned)

    cleaned = re.sub(r"[^\d.]", "", cleaned)
    cleaned = cleaned.strip(".")

    # Multiple dots resolution (e.g. 1.250.00 or 12.50.00)
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        if len(parts[-1]) <= 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        else:
            cleaned = "".join(parts)

    try:
        val = round(float(cleaned), 2)
        return -val if is_negative else val
    except (ValueError, TypeError):
        return 0.0


WORD_TO_NUM: dict[str, int] = {
    "zero": 0, "nil": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "eigh+": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

MULTIPLIERS: dict[str, int] = {
    "hundred": 100,
    "thousand": 1000,
    "lakh": 100000,
    "lac": 100000,
    "lakhs": 100000,
    "million": 1000000,
    "crore": 10000000,
    "crores": 10000000,
}


def _parse_word_phrase(phrase: str) -> float:
    """Internal helper to convert a simple phrase of number words into an integer value."""
    cleaned = phrase.lower()
    cleaned = re.sub(r"\b(?:inr|rs|rupees?|only|chargeable|amount|in|words|and)\b|[₹$£€:\-.,]", " ", cleaned)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]

    total = 0
    current = 0
    matched_any = False

    for token in tokens:
        if token in WORD_TO_NUM:
            current += WORD_TO_NUM[token]
            matched_any = True
        elif token in MULTIPLIERS:
            mult = MULTIPLIERS[token]
            if mult == 100:
                current = (current if current != 0 else 1) * 100
            else:
                current = (current if current != 0 else 1) * mult
                total += current
                current = 0
            matched_any = True
        elif token.isdigit():
            val = int(token)
            current += val
            matched_any = True

    total += current
    return float(total) if (matched_any and total >= 0) else 0.0


def words_to_number(text: str) -> float | None:
    """Convert written currency text (e.g. 'INR Eight Thousand Nine Hundred Ninety Only') to float."""
    if not text:
        return None

    # Replace hyphens between words (e.g. twenty-five -> twenty five)
    text_clean = text.replace("-", " ")

    # Check for fractional paise/cents (e.g. "and Fifty Paise" or "40/100")
    paise_val = 0.0
    frac_match = re.search(r"(\d+)\s*/\s*100", text_clean)
    if frac_match:
        paise_val = float(frac_match.group(1)) / 100.0
        text_clean = re.sub(r"\d+\s*/\s*100", "", text_clean)

    paise_match = re.search(r"\b(?:and\s+)?([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)\s*(?:paise|cents?|paisa)\b", text_clean, re.IGNORECASE)
    if paise_match:
        paise_words = paise_match.group(1).strip()
        parsed_paise = _parse_word_phrase(paise_words)
        if parsed_paise > 0:
            paise_val = round(parsed_paise / 100.0, 2)
            # Remove paise phrase from main text
            text_clean = text_clean[:paise_match.start()] + " " + text_clean[paise_match.end():]

    main_val = _parse_word_phrase(text_clean)
    if main_val > 0 or paise_val > 0:
        return round(main_val + paise_val, 2)
    return None


@dataclass
class BilateralSummary:
    left_boxes: list[dict[str, Any]] = field(default_factory=list)
    right_boxes: list[dict[str, Any]] = field(default_factory=list)
    split_x: float = 0.0
    amount_in_words: str | None = None
    terms_and_conditions: list[str] = field(default_factory=list)
    subtotal: float | None = None
    discount: float | None = None
    tax_amount: float | None = None
    cgst: float | None = None
    sgst: float | None = None
    igst: float | None = None
    round_off: float | None = None
    grand_total: float | None = None
    raw_totals: dict[str, float] = field(default_factory=dict)


class BilateralBlockSplitter:
    """Splits summary zone boxes into narrative left-block and numeric right-block."""

    def __init__(self, min_gutter_ratio: float = 0.02, default_split_ratio: float = 0.55):
        self.min_gutter_ratio = min_gutter_ratio
        self.default_split_ratio = default_split_ratio

    def find_split_x(
        self,
        summary_boxes: list[dict[str, Any]],
        doc_width: float | None = None,
    ) -> float:
        """Find optimal horizontal split point between left narrative and right totals."""
        if not summary_boxes:
            return (doc_width or 1000.0) * self.default_split_ratio

        if doc_width is None or doc_width <= 0:
            doc_width = max(b["x_max"] for b in summary_boxes) * 1.05

        # Ignore boxes that span >65% of page width (e.g. wide divider or full disclaimer)
        narrow_boxes = [b for b in summary_boxes if (b["x_max"] - b["x_min"]) < (0.65 * doc_width)]
        if not narrow_boxes:
            narrow_boxes = summary_boxes

        # Search for horizontal whitespace gutters between 30% and 75% of page width
        search_start = 0.30 * doc_width
        search_end = 0.75 * doc_width

        # Check candidate gutters
        intervals = sorted([(b["x_min"], b["x_max"]) for b in narrow_boxes], key=lambda x: x[0])

        # Merge overlapping intervals
        merged: list[tuple[float, float]] = []
        for iv in intervals:
            if not merged or iv[0] > merged[-1][1]:
                merged.append(iv)
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], iv[1]))

        # Look for gaps between merged intervals falling within the search range
        candidate_gutters: list[tuple[float, float, float]] = []  # (width, x_mid, distance_from_ideal)
        ideal_x = doc_width * self.default_split_ratio

        for i in range(len(merged) - 1):
            gap_start = merged[i][1]
            gap_end = merged[i + 1][0]
            if gap_end > gap_start:
                overlap_start = max(gap_start, search_start)
                overlap_end = min(gap_end, search_end)
                if overlap_end > overlap_start:
                    gutter_w = overlap_end - overlap_start
                    gutter_mid = (overlap_start + overlap_end) / 2.0
                    dist = abs(gutter_mid - ideal_x)
                    candidate_gutters.append((gutter_w, gutter_mid, dist))

        if candidate_gutters:
            candidate_gutters.sort(key=lambda g: (-g[0], g[2]))
            return candidate_gutters[0][1]

        # If no strict zero-overlap gap exists, find point in search range with minimal overlap
        step = max(5.0, doc_width / 200.0)
        best_x = ideal_x
        min_overlap = float("inf")

        cur_x = search_start
        while cur_x <= search_end:
            overlap_count = sum(1 for b in narrow_boxes if b["x_min"] <= cur_x <= b["x_max"])
            penalty = overlap_count + (abs(cur_x - ideal_x) / doc_width) * 0.5
            if penalty < min_overlap:
                min_overlap = penalty
                best_x = cur_x
            cur_x += step

        return best_x

    def _cluster_rows(self, boxes: list[dict[str, Any]], y_threshold: float = 20.0) -> list[list[dict[str, Any]]]:
        """Cluster boxes into horizontal rows sorted by Y coordinate."""
        if not boxes:
            return []
        sorted_boxes = sorted(boxes, key=lambda b: b.get("y", (b["y_min"] + b["y_max"]) / 2.0 if "y_min" in b else 0.0))
        rows: list[list[dict[str, Any]]] = []
        for b in sorted_boxes:
            b_y = b.get("y", (b["y_min"] + b["y_max"]) / 2.0 if "y_min" in b else 0.0)
            if not rows:
                rows.append([b])
            else:
                last_y = rows[-1][0].get("y", (rows[-1][0]["y_min"] + rows[-1][0]["y_max"]) / 2.0 if "y_min" in rows[-1][0] else 0.0)
                if abs(b_y - last_y) <= y_threshold:
                    rows[-1].append(b)
                else:
                    rows.append([b])

        for r in rows:
            r.sort(key=lambda b: b["x_min"])
        return rows

    def _extract_totals_from_rows(
        self,
        rows: list[list[dict[str, Any]]],
    ) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None, float | None, dict[str, float]]:
        """Extract subtotal, discount, CGST, SGST, IGST, round-off, and grand total from rows."""
        subtotal: float | None = None
        discount: float | None = None
        cgst: float | None = None
        sgst: float | None = None
        igst: float | None = None
        round_off: float | None = None
        grand_total: float | None = None
        raw_totals: dict[str, float] = {}

        for row in rows:
            row_text = " ".join(b["text"] for b in row).strip()
            row_lower = row_text.lower()

            numbers: list[float] = []
            for b in row:
                t = b["text"].strip()
                val = parse_numeric(t)
                if val != 0.0:
                    numbers.append(val)

            # Subtotal detection
            if any(k in row_lower for k in ["sub total", "subtotal", "sub-total", "taxable value", "taxable amount"]):
                if numbers:
                    subtotal = abs(numbers[-1])
                    raw_totals["subtotal"] = subtotal

            # Discount detection
            if any(k in row_lower for k in ["discount", "less:", "disc."]) and not any(k in row_lower for k in ["subtotal", "tax"]):
                if numbers:
                    discount = abs(numbers[-1])
                    raw_totals["discount"] = discount

            # CGST detection
            if "cgst" in row_lower:
                if numbers:
                    cgst = abs(numbers[-1])
                    raw_totals["cgst"] = cgst

            # SGST detection
            if "sgst" in row_lower:
                if numbers:
                    sgst = abs(numbers[-1])
                    raw_totals["sgst"] = sgst

            # IGST detection
            if "igst" in row_lower:
                if numbers:
                    igst = abs(numbers[-1])
                    raw_totals["igst"] = igst

            # Round off detection
            if "round" in row_lower and "off" in row_lower:
                if numbers:
                    round_off = numbers[-1]
                    raw_totals["round_off"] = round_off

            # Grand total detection (matches "grand total", "net total", "total (rs)", or standalone "total:", "total 500")
            is_gt = any(k in row_lower for k in [
                "grand total", "net total", "total (rs)", "total amount",
                "total amt", "net payable", "total payable", "invoice total", "final total", "bill total",
            ])
            if not is_gt and not any(k in row_lower for k in ["sub total", "subtotal", "taxable", "cgst", "sgst", "igst"]):
                if re.search(r"^\s*total(?:\s*[:.]|\s*\(rs\)?|\s*rs\.?|\s*₹|\s+\d|\s*$)", row_lower):
                    is_gt = True

            if is_gt and numbers:
                grand_total = abs(numbers[-1])
                raw_totals["grand_total"] = grand_total

        return subtotal, discount, cgst, sgst, igst, round_off, grand_total, raw_totals

    def split(
        self,
        summary_boxes: list[dict[str, Any]],
        doc_width: float | None = None,
    ) -> BilateralSummary:
        """Partition summary boxes into left and right blocks and extract key financial totals."""
        if not summary_boxes:
            return BilateralSummary()

        if doc_width is None or doc_width <= 0:
            doc_width = max(b["x_max"] for b in summary_boxes) * 1.05

        split_x = self.find_split_x(summary_boxes, doc_width)

        left_boxes: list[dict[str, Any]] = []
        right_boxes: list[dict[str, Any]] = []

        for b in summary_boxes:
            box_center_x = (b["x_min"] + b["x_max"]) / 2.0
            if box_center_x < split_x:
                left_boxes.append(b)
            else:
                right_boxes.append(b)

        # Parse Left Block: narrative (words, terms)
        amount_in_words: str | None = None
        terms_and_conditions: list[str] = []

        left_rows = self._cluster_rows(left_boxes, y_threshold=22.0)
        capture_words = False
        words_lines: list[str] = []

        for row in left_rows:
            row_text = " ".join(b["text"] for b in row).strip()
            row_lower = row_text.lower()

            if any(k in row_lower for k in ["amount chargeable (in words)", "amount in words", "rupees in words"]):
                capture_words = True
                cleaned = re.sub(r"(?i)amount\s+(?:chargeable\s+)?(?:\(in\s+words\)|in\s+words)[:\s]*", "", row_text).strip()
                if cleaned:
                    words_lines.append(cleaned)
                continue

            if any(k in row_lower for k in ["terms & conditions", "terms and conditions", "terms :", "terms:"]):
                capture_words = False
                cleaned = re.sub(r"(?i)terms\s*(?:&|and)?\s*conditions?[:\s]*", "", row_text).strip()
                if cleaned:
                    terms_and_conditions.append(cleaned)
                continue

            # Numbered terms: e.g. "1. Goods once sold...", "2. Subject to..."
            if re.match(r"^\d+[.)]\s*", row_text):
                terms_and_conditions.append(row_text)
                capture_words = False
                continue

            if capture_words:
                if any(w in row_lower for w in ["thousand", "hundred", "rupees", "inr", "lakh", "only", "ninety", "eight", "seven"]):
                    words_lines.append(row_text)
                else:
                    capture_words = False

        if words_lines:
            amount_in_words = " ".join(words_lines).strip()
        elif left_boxes:
            for b in left_boxes:
                t = b["text"].strip()
                if re.search(r"\b(?:inr|rupees?)\b.*\b(?:only)\b", t, re.IGNORECASE):
                    amount_in_words = t
                    break

        # Parse Right Block: accounting totals
        right_rows = self._cluster_rows(right_boxes, y_threshold=22.0)
        subtotal, discount, cgst, sgst, igst, round_off, grand_total, raw_totals = self._extract_totals_from_rows(right_rows)

        # Fallback: if no totals were found in right_boxes (e.g. left-aligned receipts or narrow columns),
        # scan left_boxes for accounting totals
        if subtotal is None and grand_total is None and left_rows:
            l_sub, l_disc, l_cgst, l_sgst, l_igst, l_ro, l_gt, l_raw = self._extract_totals_from_rows(left_rows)
            if l_sub is not None or l_gt is not None:
                subtotal = l_sub
                discount = l_disc
                cgst = l_cgst
                sgst = l_sgst
                igst = l_igst
                round_off = l_ro
                grand_total = l_gt
                raw_totals.update(l_raw)

        # Percentage rate check for CGST/SGST against subtotal (e.g. CGST @ 9% of 7580 = 682.20)
        all_summary_rows = right_rows + left_rows
        for row in all_summary_rows:
            row_text = " ".join(b["text"] for b in row).lower()
            pct_m = re.search(r"@\s*(\d+(?:\.\d+)?)\s*%", row_text)
            if pct_m and subtotal and subtotal > 0:
                rate_pct = float(pct_m.group(1))
                expected_tax = round(subtotal * (rate_pct / 100.0), 2)
                if "cgst" in row_text:
                    if cgst is None or cgst < expected_tax * 0.5 or abs(cgst - expected_tax) > 1.0:
                        logger.info(f"Correcting CGST from percentage math: {cgst} -> {expected_tax}")
                        cgst = expected_tax
                        raw_totals["cgst"] = cgst
                elif "sgst" in row_text:
                    if sgst is None or sgst < expected_tax * 0.5 or abs(sgst - expected_tax) > 1.0:
                        logger.info(f"Correcting SGST from percentage math: {sgst} -> {expected_tax}")
                        sgst = expected_tax
                        raw_totals["sgst"] = sgst

        # Symmetric Digit Confusion Repair for Indian GST (CGST == SGST by law when tax rates match)
        if cgst is not None and sgst is not None and abs(cgst - sgst) > 1.0:
            sgst_str = f"{sgst:.2f}"
            cgst_str = f"{cgst:.2f}"
            if cgst > sgst:
                # SGST dropped leading digit or confused (e.g. 682.20 vs 82.20)
                if (
                    (len(sgst_str) == len(cgst_str) and sgst_str[1:] == cgst_str[1:])
                    or (len(cgst_str) == len(sgst_str) + 1 and cgst_str[1:] == sgst_str)
                    or (subtotal and abs(round(subtotal * 0.09, 2) - cgst) < 1.0)
                ):
                    logger.info(f"Repairing SGST digit confusion: {sgst} -> {cgst}")
                    sgst = cgst
                    raw_totals["sgst"] = sgst
            elif sgst > cgst:
                # CGST dropped leading digit or confused
                if (
                    (len(cgst_str) == len(sgst_str) and cgst_str[1:] == sgst_str[1:])
                    or (len(sgst_str) == len(cgst_str) + 1 and sgst_str[1:] == cgst_str)
                    or (subtotal and abs(round(subtotal * 0.09, 2) - sgst) < 1.0)
                ):
                    logger.info(f"Repairing CGST digit confusion: {cgst} -> {sgst}")
                    cgst = sgst
                    raw_totals["cgst"] = cgst

        # Total tax calculation
        tax_amount: float | None = None
        if cgst is not None and sgst is not None:
            tax_amount = round(cgst + sgst, 2)
        elif igst is not None:
            tax_amount = igst
        elif cgst is not None:
            tax_amount = cgst
        elif sgst is not None:
            tax_amount = sgst

        # Grand total fallback from amount_in_words
        is_garbled_grand_total = (
            grand_total is None
            or grand_total <= 0
            or (subtotal is not None and grand_total < subtotal * 0.5)
        )
        if is_garbled_grand_total and amount_in_words:
            words_num = words_to_number(amount_in_words)
            if words_num and words_num > 0:
                grand_total = words_num
                raw_totals["grand_total"] = grand_total

        # Grand total arithmetic calculation fallback
        if (grand_total is None or (subtotal is not None and grand_total < subtotal * 0.5)) and subtotal is not None:
            calc_total = subtotal + (tax_amount or 0.0) - (discount or 0.0) + (round_off or 0.0)
            if calc_total > 0:
                grand_total = round(calc_total, 2)
                raw_totals["grand_total"] = grand_total

        # If subtotal missing but grand_total and taxes are present
        if subtotal is None and grand_total is not None:
            if tax_amount:
                subtotal = round(grand_total - tax_amount + (discount or 0.0) - (round_off or 0.0), 2)
            else:
                subtotal = grand_total
            raw_totals["subtotal"] = subtotal

        return BilateralSummary(
            left_boxes=left_boxes,
            right_boxes=right_boxes,
            split_x=split_x,
            amount_in_words=amount_in_words,
            terms_and_conditions=terms_and_conditions,
            subtotal=subtotal,
            discount=discount,
            tax_amount=tax_amount,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            round_off=round_off,
            grand_total=grand_total,
            raw_totals=raw_totals,
        )
