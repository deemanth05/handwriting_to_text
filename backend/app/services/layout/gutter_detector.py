"""Adaptive Column Detector for Document Tables.

Uses 1D horizontal projection profiles, whitespace valley analysis, and header anchors
to discover column intervals on any 3-to-7+ column table (Invoices, Khatas, Petty Cash books).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations, permutations
import logging
import re
from typing import Any

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.layout.bilateral_splitter import parse_numeric

logger = logging.getLogger(__name__)


class ColumnType(str, Enum):
    INDEX = "INDEX"
    DESCRIPTION = "DESCRIPTION"
    QUANTITY = "QUANTITY"
    UNIT = "UNIT"
    RATE = "RATE"
    TOTAL = "TOTAL"
    DATE = "DATE"
    VOUCHER = "VOUCHER"
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    BALANCE = "BALANCE"
    HSN = "HSN"
    UNKNOWN = "UNKNOWN"


@dataclass
class ColumnInterval:
    col_id: int
    col_type: ColumnType
    x_start: float
    x_end: float
    header_text: str | None = None
    confidence: float = 1.0


class AdaptiveColumnDetector:
    """Discovers column intervals and maps horizontal table cells into structured row schemas."""

    def __init__(
        self,
        min_gutter_width_px: float | None = None,
        density_threshold: float = 0.15,
        bin_size_px: float = 4.0,
    ):
        self.min_gutter_width_px = (
            min_gutter_width_px
            if min_gutter_width_px is not None
            else getattr(settings, "LAYOUT_GUTTER_MIN_WIDTH_PX", 12.0)
        )
        self.density_threshold = density_threshold
        self.bin_size_px = bin_size_px

    def _classify_header_token(self, text: str, doc_type: DocumentType) -> ColumnType:
        """Map header text to semantic ColumnType."""
        t = text.lower().strip()

        if doc_type in [DocumentType.CASH_BOOK, DocumentType.KHATA_LEDGER]:
            if any(k in t for k in ["date", "dinank", "dt", "tarikh"]):
                return ColumnType.DATE
            if any(k in t for k in ["voucher", "v.no", "vr.no", "vr no", "vno"]):
                return ColumnType.VOUCHER
            if any(k in t for k in ["detail", "particular", "desc", "narration", "head"]):
                return ColumnType.DESCRIPTION
            if any(k in t for k in ["out", "debit", "dr", "paid", "payment", "jama"]):
                return ColumnType.DEBIT
            if any(k in t for k in ["in", "credit", "cr", "received", "receipt", "naam"]):
                return ColumnType.CREDIT
            if any(k in t for k in ["bal", "balance", "baki"]):
                return ColumnType.BALANCE
            if any(k in t for k in ["amount", "rakkam"]):
                return ColumnType.DEBIT

        # Invoice types
        if re.search(r"\b(?:s\.?n\.?o?|sr\.?|sl\.?|item\s*no|#)\b", t):
            return ColumnType.INDEX
        if any(k in t for k in ["hsn", "sac"]):
            return ColumnType.HSN
        if any(k in t for k in ["description", "particular", "item", "product", "goods", "vigaran"]):
            return ColumnType.DESCRIPTION
        if re.search(r"\b(?:unit\s*price|unit\s*rate|rate|price|mrp|dar)\b", t):
            return ColumnType.RATE
        if re.search(r"\b(?:qty|quantity|qnty|nos|qnt)\b", t):
            return ColumnType.QUANTITY
        if re.search(r"\b(?:unit|units|uom)\b", t):
            return ColumnType.UNIT
        if re.search(r"\b(?:amount|total|value|rakkam)\b", t):
            return ColumnType.TOTAL
        if any(k in t for k in ["date", "dinank"]):
            return ColumnType.DATE

        return ColumnType.UNKNOWN

    def detect_columns(
        self,
        table_rows: list[list[dict[str, Any]]],
        table_header_row: list[dict[str, Any]] | None = None,
        doc_width: float | None = None,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> list[ColumnInterval]:
        """Discover column intervals using header anchors or horizontal projection valleys."""
        all_boxes = [b for r in table_rows for b in r]
        if table_header_row:
            all_boxes.extend(table_header_row)

        if not all_boxes:
            return []

        if doc_width is None or doc_width <= 0:
            doc_width = max(b["x_max"] for b in all_boxes) * 1.05

        # Approach 1: Header-guided column intervals (most accurate when table header exists)
        if table_header_row and len(table_header_row) >= 2:
            sorted_headers = sorted(table_header_row, key=lambda b: b["x_min"])
            columns: list[ColumnInterval] = []
            num_cols = len(sorted_headers)

            for i, h in enumerate(sorted_headers):
                c_type = self._classify_header_token(h["text"], doc_type)

                # Determine x_start and x_end boundaries
                if i == 0:
                    x_start = 0.0
                else:
                    prev_h = sorted_headers[i - 1]
                    x_start = (prev_h["x_max"] + h["x_min"]) / 2.0

                if i == num_cols - 1:
                    x_end = doc_width
                else:
                    next_h = sorted_headers[i + 1]
                    x_end = (h["x_max"] + next_h["x_min"]) / 2.0

                columns.append(ColumnInterval(
                    col_id=i,
                    col_type=c_type,
                    x_start=x_start,
                    x_end=x_end,
                    header_text=h["text"],
                    confidence=0.95,
                ))

            self._refine_column_types(columns, doc_type, table_rows)
            return columns

        # Approach 2: 1D Horizontal Projection Whitespace Valley Detection
        return self._detect_columns_projection(table_rows, doc_width, doc_type)

    def _detect_columns_projection(
        self,
        table_rows: list[list[dict[str, Any]]],
        doc_width: float,
        doc_type: DocumentType,
    ) -> list[ColumnInterval]:
        """Detect column intervals purely via whitespace valleys in 1D horizontal projection."""
        all_boxes = [b for r in table_rows for b in r]
        if not all_boxes:
            return []

        min_table_x = min(b["x_min"] for b in all_boxes)
        max_table_x = max(b["x_max"] for b in all_boxes)

        num_bins = max(10, int(doc_width / self.bin_size_px))
        occupancy = [0] * num_bins
        total_rows = max(1, len(table_rows))

        for row in table_rows:
            row_bins = set()
            for b in row:
                start_bin = max(0, int(b["x_min"] / self.bin_size_px))
                end_bin = min(num_bins - 1, int(b["x_max"] / self.bin_size_px))
                for bin_idx in range(start_bin, end_bin + 1):
                    row_bins.add(bin_idx)
            for bin_idx in row_bins:
                occupancy[bin_idx] += 1

        density = [count / float(total_rows) for count in occupancy]

        # Identify valleys
        is_valley = [d <= self.density_threshold for d in density]

        # Group contiguous valley bins of width >= min_gutter_width_px
        min_bins = max(1, int(self.min_gutter_width_px / self.bin_size_px))
        gutters: list[tuple[float, float]] = []
        cur_start: int | None = None

        for idx, val in enumerate(is_valley):
            if val and cur_start is None:
                cur_start = idx
            elif not val and cur_start is not None:
                if (idx - cur_start) >= min_bins:
                    gutters.append((cur_start * self.bin_size_px, idx * self.bin_size_px))
                cur_start = None

        if cur_start is not None and (len(is_valley) - cur_start) >= min_bins:
            gutters.append((cur_start * self.bin_size_px, len(is_valley) * self.bin_size_px))

        # Filter out external gutters (left/right outer page margins)
        # Internal gutters must start after min_table_x and end before max_table_x
        margin_thresh = 15.0
        internal_gutters: list[tuple[float, float]] = []
        for g_start, g_end in gutters:
            if g_end > min_table_x + margin_thresh and g_start < max_table_x - margin_thresh:
                internal_gutters.append((max(g_start, min_table_x), min(g_end, max_table_x)))

        # Build column intervals between internal gutters
        cols: list[tuple[float, float]] = []
        last_x = 0.0
        for g_start, g_end in internal_gutters:
            g_mid = (g_start + g_end) / 2.0
            if g_mid > last_x + 20.0:
                cols.append((last_x, g_mid))
                last_x = g_mid
        if doc_width > last_x + 20.0:
            cols.append((last_x, doc_width))

        if not cols:
            # Fallback to standard 4 columns
            cols = [
                (0.0, 0.45 * doc_width),
                (0.45 * doc_width, 0.60 * doc_width),
                (0.60 * doc_width, 0.80 * doc_width),
                (0.80 * doc_width, doc_width),
            ]

        columns: list[ColumnInterval] = []
        for i, (xs, xe) in enumerate(cols):
            columns.append(ColumnInterval(
                col_id=i,
                col_type=ColumnType.UNKNOWN,
                x_start=xs,
                x_end=xe,
                confidence=0.75,
            ))

        self._refine_column_types(columns, doc_type, table_rows)
        return columns

    def _refine_column_types(
        self,
        columns: list[ColumnInterval],
        doc_type: DocumentType,
        table_rows: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        """Infer unknown column types based on typical column ordering and contents."""
        num_cols = len(columns)

        if doc_type in [DocumentType.CASH_BOOK, DocumentType.KHATA_LEDGER]:
            if num_cols >= 6:
                if columns[0].col_type == ColumnType.UNKNOWN:
                    columns[0].col_type = ColumnType.DATE
                if columns[1].col_type == ColumnType.UNKNOWN:
                    columns[1].col_type = ColumnType.VOUCHER
                if columns[2].col_type == ColumnType.UNKNOWN:
                    columns[2].col_type = ColumnType.DESCRIPTION
                if columns[3].col_type == ColumnType.UNKNOWN:
                    columns[3].col_type = ColumnType.DEBIT
                if columns[4].col_type == ColumnType.UNKNOWN:
                    columns[4].col_type = ColumnType.CREDIT
                if columns[5].col_type == ColumnType.UNKNOWN:
                    columns[5].col_type = ColumnType.BALANCE
            elif num_cols == 5:
                if columns[0].col_type == ColumnType.UNKNOWN:
                    columns[0].col_type = ColumnType.DATE
                if columns[1].col_type == ColumnType.UNKNOWN:
                    columns[1].col_type = ColumnType.DESCRIPTION
                if columns[2].col_type == ColumnType.UNKNOWN:
                    columns[2].col_type = ColumnType.DEBIT
                if columns[3].col_type == ColumnType.UNKNOWN:
                    columns[3].col_type = ColumnType.CREDIT
                if columns[4].col_type == ColumnType.UNKNOWN:
                    columns[4].col_type = ColumnType.BALANCE
            elif num_cols == 4:
                if columns[0].col_type == ColumnType.UNKNOWN:
                    columns[0].col_type = ColumnType.DATE
                if columns[1].col_type == ColumnType.UNKNOWN:
                    columns[1].col_type = ColumnType.DESCRIPTION
                if columns[2].col_type == ColumnType.UNKNOWN:
                    columns[2].col_type = ColumnType.DEBIT
                if columns[3].col_type == ColumnType.UNKNOWN:
                    columns[3].col_type = ColumnType.BALANCE
            return

        # Invoice types: [Index], Description, [Qty], [Rate], Total
        known_types = {c.col_type for c in columns}

        if ColumnType.DESCRIPTION not in known_types:
            desc_candidates = [c for c in columns if c.col_type in [ColumnType.UNKNOWN, ColumnType.INDEX]]
            if desc_candidates:
                widest = max(desc_candidates, key=lambda c: c.x_end - c.x_start)
                widest.col_type = ColumnType.DESCRIPTION

        if ColumnType.TOTAL not in known_types:
            if columns[-1].col_type == ColumnType.UNKNOWN:
                columns[-1].col_type = ColumnType.TOTAL

        if num_cols >= 7:
            # 7-column GST invoice: S.No, Description, HSN, Qty, Unit, Rate, Total
            if columns[0].col_type == ColumnType.UNKNOWN:
                columns[0].col_type = ColumnType.INDEX
            if columns[1].col_type == ColumnType.UNKNOWN:
                columns[1].col_type = ColumnType.DESCRIPTION
            if columns[2].col_type == ColumnType.UNKNOWN:
                columns[2].col_type = ColumnType.HSN
            if columns[3].col_type == ColumnType.UNKNOWN:
                columns[3].col_type = ColumnType.QUANTITY
            if columns[4].col_type == ColumnType.UNKNOWN:
                columns[4].col_type = ColumnType.UNIT
            if columns[5].col_type == ColumnType.UNKNOWN:
                columns[5].col_type = ColumnType.RATE
            if columns[6].col_type == ColumnType.UNKNOWN:
                columns[6].col_type = ColumnType.TOTAL
        elif num_cols == 5:
            if columns[0].col_type == ColumnType.UNKNOWN:
                columns[0].col_type = ColumnType.INDEX
            if columns[1].col_type == ColumnType.UNKNOWN:
                columns[1].col_type = ColumnType.DESCRIPTION
            if columns[2].col_type == ColumnType.UNKNOWN:
                columns[2].col_type = ColumnType.QUANTITY
            if columns[3].col_type == ColumnType.UNKNOWN:
                columns[3].col_type = ColumnType.RATE
            if columns[4].col_type == ColumnType.UNKNOWN:
                columns[4].col_type = ColumnType.TOTAL
        elif num_cols == 4:
            if columns[0].col_type == ColumnType.UNKNOWN:
                columns[0].col_type = ColumnType.DESCRIPTION
            if columns[1].col_type == ColumnType.UNKNOWN:
                columns[1].col_type = ColumnType.QUANTITY
            if columns[2].col_type == ColumnType.UNKNOWN:
                columns[2].col_type = ColumnType.RATE
            if columns[3].col_type == ColumnType.UNKNOWN:
                columns[3].col_type = ColumnType.TOTAL
        elif num_cols == 3:
            if columns[0].col_type == ColumnType.UNKNOWN:
                columns[0].col_type = ColumnType.DESCRIPTION
            if columns[2].col_type == ColumnType.UNKNOWN:
                columns[2].col_type = ColumnType.TOTAL
            if columns[1].col_type == ColumnType.UNKNOWN:
                # Inspect values in column 1 to decide between QUANTITY and RATE
                col1_vals: list[float] = []
                if table_rows:
                    for r in table_rows:
                        for b in r:
                            bx_mid = (b["x_min"] + b["x_max"]) / 2.0
                            if columns[1].x_start <= bx_mid <= columns[1].x_end:
                                v = parse_numeric(b["text"])
                                if v > 0:
                                    col1_vals.append(v)
                if col1_vals and all(v == int(v) for v in col1_vals):
                    columns[1].col_type = ColumnType.QUANTITY
                else:
                    columns[1].col_type = ColumnType.RATE

    def map_box_to_column(self, box: dict[str, Any], columns: list[ColumnInterval]) -> ColumnInterval:
        """Assign an individual bounding box to the best matching column interval."""
        bx_min = box["x_min"]
        bx_max = box["x_max"]
        bx_mid = (bx_min + bx_max) / 2.0

        best_col = columns[0]
        max_overlap = -1.0

        for col in columns:
            overlap_start = max(bx_min, col.x_start)
            overlap_end = min(bx_max, col.x_end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > max_overlap:
                max_overlap = overlap
                best_col = col

        # If zero overlap (e.g. box fell right into a gutter gap), assign by midpoint distance
        if max_overlap <= 0.0:
            min_dist = float("inf")
            for col in columns:
                col_mid = (col.x_start + col.x_end) / 2.0
                dist = abs(bx_mid - col_mid)
                if dist < min_dist:
                    min_dist = dist
                    best_col = col

        return best_col

    def _is_predominantly_numeric(self, text: str, col_type: ColumnType) -> bool:
        """Check if a text box represents a financial numeric value rather than a narrative description."""
        t_clean = re.sub(r"[₹$£€]|rs\.?|inr", "", text, flags=re.IGNORECASE).strip()
        if not t_clean:
            return False

        # Pure numbers, decimals, or thousand-separated amounts
        if re.match(r"^\d+(?:[.,:]\d+)?$", t_clean) or re.match(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$", t_clean):
            return True

        # Number with unit suffix (e.g. "10 nos", "5 pcs", "2.5 kg")
        if re.match(r"^\d+(?:[.,:]\d+)?\s*(?:nos|pcs|kg|mtr|m|units?|box|gm|pkts?|set)?$", t_clean, re.IGNORECASE):
            return True

        # Number in numeric column: must have more digits than letters
        if col_type in [ColumnType.QUANTITY, ColumnType.RATE, ColumnType.TOTAL, ColumnType.DEBIT, ColumnType.CREDIT, ColumnType.BALANCE]:
            digits_count = sum(c.isdigit() for c in t_clean)
            letters_count = sum(c.isalpha() for c in t_clean)
            if digits_count > 0 and digits_count >= letters_count:
                return True

        return False

    def parse_invoice_items(
        self,
        table_rows: list[list[dict[str, Any]]],
        columns: list[ColumnInterval],
    ) -> list[dict[str, Any]]:
        """Extract structured line items with mathematical validation and quantity recovery."""
        line_items: list[dict[str, Any]] = []

        for row in table_rows:
            col_boxes: dict[ColumnType, list[dict[str, Any]]] = {ct: [] for ct in ColumnType}
            all_numbers: list[tuple[float, dict[str, Any]]] = []

            for b in row:
                col = self.map_box_to_column(b, columns)
                col_boxes[col.col_type].append(b)

                if self._is_predominantly_numeric(b["text"], col.col_type):
                    val = parse_numeric(b["text"])
                    if val > 0:
                        all_numbers.append((val, b))

            # Assemble description (exclude any boxes that were identified as financial numbers)
            num_boxes_set = {id(nb[1]) for nb in all_numbers}
            desc_parts: list[str] = [
                b["text"].strip() for b in col_boxes[ColumnType.DESCRIPTION] if id(b) not in num_boxes_set
            ]
            if not desc_parts:
                # If no box directly fell into DESCRIPTION, use non-numeric boxes to the left of the numbers
                if all_numbers:
                    first_num_x = min(nb[1]["x_min"] for nb in all_numbers)
                    desc_parts = [
                        b["text"].strip()
                        for b in row
                        if b["x_max"] <= first_num_x and id(b) not in num_boxes_set
                    ]
                if not desc_parts:
                    desc_parts = [b["text"].strip() for b in row if id(b) not in num_boxes_set]

            desc = " ".join(desc_parts).strip()
            desc_lower = desc.lower()

            # Ignore header remnants or summary totals
            if any(k in desc_lower for k in [
                "description", "particular", "rate", "qty", "amount", "total (rs)",
                "rakkam", "sub total", "grand total", "terms & conditions",
            ]):
                continue

            if desc_lower in ["total", "total:", "total.", "total (rs)", "total rs", "sub total", "subtotal", "grand total", "net total"]:
                continue
            if re.search(r"^\s*(?:s\.?no\.?\s*)?total(?:\s*[:.]|\s*\(rs\)?|\s*rs\.?|\s*₹|\s*$)", desc_lower):
                continue

            # A valid invoice line item must contain financial numbers (price/amount/quantity)
            if not all_numbers:
                continue

            # Column-assigned values
            col_qty: float | None = None
            col_rate: float | None = None
            col_total: float | None = None

            if col_boxes[ColumnType.QUANTITY]:
                q_vals = [parse_numeric(b["text"]) for b in col_boxes[ColumnType.QUANTITY] if parse_numeric(b["text"]) > 0]
                if q_vals:
                    col_qty = q_vals[0]

            if col_boxes[ColumnType.RATE]:
                r_vals = [parse_numeric(b["text"]) for b in col_boxes[ColumnType.RATE] if parse_numeric(b["text"]) > 0]
                if r_vals:
                    col_rate = r_vals[0]

            if col_boxes[ColumnType.TOTAL]:
                t_vals = [parse_numeric(b["text"]) for b in col_boxes[ColumnType.TOTAL] if parse_numeric(b["text"]) > 0]
                if t_vals:
                    col_total = t_vals[-1]

            # Mathematical reconciliation / permutation check
            numbers = [val for val, _ in all_numbers]
            assigned = False

            if col_qty is not None and col_rate is not None and col_total is not None:
                if abs(col_qty * col_rate - col_total) <= 0.05 * col_total or abs(col_qty * col_rate - col_total) <= 1.0:
                    line_items.append({
                        "description": desc,
                        "quantity": col_qty,
                        "unit_price": col_rate,
                        "line_total": col_total,
                    })
                    continue

            # If 3 or more numbers exist in row, try permutations
            if len(numbers) >= 3:
                candidate_triplets = [numbers[-3:]]
                if len(numbers) > 3:
                    for comb in combinations(numbers, 3):
                        if list(comb) != numbers[-3:]:
                            candidate_triplets.append(list(comb))

                for triplet in candidate_triplets:
                    valid_perms = []
                    for q_cand, p_cand, t_cand in permutations(triplet, 3):
                        if q_cand > 0 and p_cand > 0 and abs(q_cand * p_cand - t_cand) <= max(0.05, 0.02 * t_cand):
                            valid_perms.append((q_cand, p_cand, t_cand))

                    if valid_perms:
                        best = None
                        for q_cand, p_cand, t_cand in valid_perms:
                            if t_cand == triplet[-1] and q_cand == triplet[0] and p_cand == triplet[1]:
                                best = (q_cand, p_cand, t_cand)
                                break
                        if not best:
                            for q_cand, p_cand, t_cand in valid_perms:
                                if t_cand == triplet[-1]:
                                    best = (q_cand, p_cand, t_cand)
                                    break
                        if not best:
                            best = valid_perms[0]

                        q, p, t = best
                        line_items.append({
                            "description": desc,
                            "quantity": q,
                            "unit_price": p,
                            "line_total": t,
                        })
                        assigned = True
                        break

            if assigned:
                continue

            # Fallback 0: 3 or more numbers present, preserve numbers[-3] as quantity, numbers[-2] as rate, numbers[-1] as total
            if len(numbers) >= 3:
                line_items.append({
                    "description": desc,
                    "quantity": numbers[-3],
                    "unit_price": numbers[-2],
                    "line_total": numbers[-1],
                })
                continue

            # Fallback 1a: Rate and Total present, recover Quantity mathematically
            if col_rate is not None and col_total is not None and col_rate > 0:
                recovered_qty = round(col_total / col_rate, 2)
                line_items.append({
                    "description": desc,
                    "quantity": recovered_qty,
                    "unit_price": col_rate,
                    "line_total": col_total,
                })
                continue

            # Fallback 1b: Quantity and Total present, recover Rate mathematically
            if col_qty is not None and col_total is not None and col_qty > 0:
                recovered_rate = round(col_total / col_qty, 2)
                line_items.append({
                    "description": desc,
                    "quantity": col_qty,
                    "unit_price": recovered_rate,
                    "line_total": col_total,
                })
                continue

            # Fallback 2: Exactly 2 numbers in row
            if len(numbers) == 2:
                if col_qty is not None:
                    q = col_qty
                    t = numbers[-1]
                    p = round(t / q, 2) if q > 0 else t
                elif col_rate is not None:
                    p = col_rate
                    t = numbers[-1]
                    q = round(t / p, 2) if p > 0 else 1.0
                else:
                    # Heuristic: if numbers[0] is small integer (<= 50) and numbers[1] >= numbers[0]:
                    if numbers[0] == int(numbers[0]) and numbers[0] <= 50 and numbers[1] >= numbers[0]:
                        q = numbers[0]
                        t = numbers[1]
                        p = round(t / q, 2)
                    else:
                        p = numbers[0]
                        t = numbers[1]
                        q = round(t / p, 2) if p > 0 else 1.0

                line_items.append({
                    "description": desc,
                    "quantity": q,
                    "unit_price": p,
                    "line_total": t,
                })
                continue

            # Fallback 3: Exactly 1 number (total)
            if len(numbers) == 1:
                t = numbers[0]
                line_items.append({
                    "description": desc,
                    "quantity": 1.0,
                    "unit_price": t,
                    "line_total": t,
                })
                continue

            # Fallback 4: Standard default from column assignments or 1.0
            line_items.append({
                "description": desc,
                "quantity": col_qty or 1.0,
                "unit_price": col_rate or col_total or 0.0,
                "line_total": col_total or (col_rate if col_rate else 0.0),
            })

        return line_items

    def parse_cash_book_items(
        self,
        table_rows: list[list[dict[str, Any]]],
        columns: list[ColumnInterval],
    ) -> list[dict[str, Any]]:
        """Extract structured ledger items for Cash Books and Khatas."""
        ledger_items: list[dict[str, Any]] = []

        for row in table_rows:
            col_boxes: dict[ColumnType, list[dict[str, Any]]] = {ct: [] for ct in ColumnType}
            for b in row:
                col = self.map_box_to_column(b, columns)
                col_boxes[col.col_type].append(b)

            # Date
            date_val: str | None = None
            date_candidates = [b["text"].strip() for b in col_boxes[ColumnType.DATE]]
            for dt in date_candidates:
                date_match = re.search(r"([0-9QOL]{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", dt)
                if date_match:
                    date_val = date_match.group(1).replace("Q", "0").replace("O", "0").replace("L", "1")
                    break

            if not date_val and row:
                date_match = re.search(r"^([0-9QOL]{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", row[0]["text"].strip())
                if date_match:
                    date_val = date_match.group(1).replace("Q", "0").replace("O", "0").replace("L", "1")

            # Voucher number
            voucher_val: str | None = None
            if col_boxes[ColumnType.VOUCHER]:
                voucher_val = col_boxes[ColumnType.VOUCHER][0]["text"].strip()

            # Particulars
            particulars_parts = [b["text"].strip() for b in col_boxes[ColumnType.DESCRIPTION]]
            if not particulars_parts:
                # Fallback: inspect boxes in UNKNOWN columns or non-numeric boxes
                non_desc_candidates: list[str] = []
                for b in row:
                    col = self.map_box_to_column(b, columns)
                    if col.col_type in [ColumnType.UNKNOWN, ColumnType.INDEX]:
                        non_desc_candidates.append(b["text"].strip())
                    elif col.col_type not in [ColumnType.DATE, ColumnType.VOUCHER, ColumnType.DEBIT, ColumnType.CREDIT, ColumnType.BALANCE]:
                        if parse_numeric(b["text"]) == 0.0:
                            non_desc_candidates.append(b["text"].strip())
                if not non_desc_candidates:
                    for b in row:
                        t = b["text"].strip()
                        if parse_numeric(t) == 0.0 and not re.search(r"^\d{1,2}[/-]\d{1,2}", t):
                            non_desc_candidates.append(t)
                particulars_parts = non_desc_candidates

            if date_val and particulars_parts and date_val in particulars_parts[0]:
                particulars_parts[0] = particulars_parts[0].replace(date_val, "").strip()
            particulars = " ".join(p for p in particulars_parts if p).strip()

            # Debit / Out
            out_val: float = 0.0
            if col_boxes[ColumnType.DEBIT]:
                out_vals = [parse_numeric(b["text"]) for b in col_boxes[ColumnType.DEBIT] if parse_numeric(b["text"]) > 0]
                if out_vals:
                    out_val = out_vals[0]

            # Credit / In
            in_val: float = 0.0
            if col_boxes[ColumnType.CREDIT]:
                in_vals = [parse_numeric(b["text"]) for b in col_boxes[ColumnType.CREDIT] if parse_numeric(b["text"]) > 0]
                if in_vals:
                    in_val = in_vals[0]

            # Running Balance
            bal_val: float = 0.0
            if col_boxes[ColumnType.BALANCE]:
                bal_vals = [parse_numeric(b["text"]) for b in col_boxes[ColumnType.BALANCE] if parse_numeric(b["text"]) > 0]
                if bal_vals:
                    bal_val = bal_vals[-1]

            # Skip header repeats or empty rows
            row_str = " ".join(b["text"].lower() for b in row)
            if any(k in row_str for k in ["page no", "petty cash", "month:", "details", "balance"]):
                if not date_val and out_val == 0.0 and in_val == 0.0 and bal_val == 0.0:
                    continue

            if not particulars and out_val == 0.0 and in_val == 0.0 and bal_val == 0.0:
                continue

            ledger_items.append({
                "entry_date": date_val,
                "particulars": particulars,
                "voucher_no": voucher_val,
                "cash_out_debit": out_val,
                "cash_in_credit": in_val,
                "running_balance": bal_val,
            })

        return ledger_items
