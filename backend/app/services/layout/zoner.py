"""Document Macro-Zoner for Financial and Tabular Documents.

Segments raw OCR text and bounding boxes into four distinct functional regions:
1. HEADER_ZONE: Vendor metadata, buyer details, dates, invoice/voucher numbers.
2. TABLE_ZONE: Column headers and line items / ledger rows.
3. SUMMARY_ZONE: Totals, tax breakdown, amounts in words, terms & conditions.
4. FOOTER_ZONE: Signatures, remarks, bank disclaimers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import logging
import re
from typing import Any

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.layout.bilateral_splitter import (
    BilateralBlockSplitter,
    BilateralSummary,
)

logger = logging.getLogger(__name__)


@dataclass
class DocumentZones:
    header_boxes: list[dict[str, Any]] = field(default_factory=list)
    table_header_row: list[dict[str, Any]] | None = None
    table_rows: list[list[dict[str, Any]]] = field(default_factory=list)
    summary_boxes: list[dict[str, Any]] = field(default_factory=list)
    footer_boxes: list[dict[str, Any]] = field(default_factory=list)
    summary_left_boxes: list[dict[str, Any]] = field(default_factory=list)
    summary_right_boxes: list[dict[str, Any]] = field(default_factory=list)
    bilateral_summary: BilateralSummary | None = None


class DocumentMacroZoner:
    """Enterprise document macro-zoner using anchor detection and geometric boundaries."""

    def __init__(
        self,
        row_merge_tolerance_px: float | None = None,
        summary_split_ratio: float | None = None,
    ):
        self.row_merge_tolerance_px = (
            row_merge_tolerance_px
            if row_merge_tolerance_px is not None
            else getattr(settings, "LAYOUT_ROW_MERGE_TOLERANCE_PX", 16.0)
        )
        self.summary_split_ratio = (
            summary_split_ratio
            if summary_split_ratio is not None
            else getattr(settings, "LAYOUT_SUMMARY_SPLIT_RATIO", 0.55)
        )
        self.splitter = BilateralBlockSplitter(default_split_ratio=self.summary_split_ratio)

    def standardize_boxes(self, raw_boxes: list[Any]) -> list[dict[str, Any]]:
        """Normalize various OCR box formats (RapidOCR tuples, Surya dicts, objects) to canonical dict."""
        normalized: list[dict[str, Any]] = []
        for item in raw_boxes:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                # RapidOCR format: [box, text, score]
                box = item[0]
                text = str(item[1]).strip()
                score = float(item[2]) if len(item) > 2 and item[2] is not None else 0.85
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                normalized.append({
                    "text": text,
                    "score": score,
                    "x_min": min(xs),
                    "x_max": max(xs),
                    "y_min": min(ys),
                    "y_max": max(ys),
                    "y": sum(ys) / 4.0,
                    "box": box,
                })
            elif isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if not text and "html" in item:
                    text = re.sub(r"<[^>]+>", "", item["html"]).strip()
                    text = html.unescape(text)

                score = float(item.get("score", item.get("confidence", 0.85)) or 0.85)
                bbox = item.get("bbox")
                polygon = item.get("polygon")
                box = item.get("box")

                if bbox and len(bbox) == 4:
                    x_min, y_min, x_max, y_max = bbox
                    y_center = (y_min + y_max) / 2.0
                elif polygon and len(polygon) >= 4:
                    xs = [p[0] for p in polygon]
                    ys = [p[1] for p in polygon]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    y_center = sum(ys) / float(len(ys))
                elif box and len(box) >= 4:
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    y_center = sum(ys) / float(len(ys))
                else:
                    x_min = float(item.get("x_min", 0.0))
                    x_max = float(item.get("x_max", 0.0))
                    y_min = float(item.get("y_min", item.get("y", 0.0)))
                    y_max = float(item.get("y_max", item.get("y", 0.0)))
                    y_center = float(item.get("y", (y_min + y_max) / 2.0))

                if text:
                    normalized.append({
                        "text": text,
                        "score": score,
                        "x_min": x_min,
                        "x_max": x_max,
                        "y_min": y_min,
                        "y_max": y_max,
                        "y": y_center,
                        "box": box or [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]],
                    })
            else:
                # Attribute-based object (e.g. Surya TextLine or BlockOCRResult)
                text = str(getattr(item, "text", "")).strip()
                if not text and hasattr(item, "html"):
                    text = re.sub(r"<[^>]+>", "", getattr(item, "html", "")).strip()
                    text = html.unescape(text)

                conf = float(getattr(item, "confidence", 0.85) or 0.85)
                bbox = getattr(item, "bbox", None)
                polygon = getattr(item, "polygon", None)

                if bbox and len(bbox) == 4:
                    x_min, y_min, x_max, y_max = bbox
                    y_center = (y_min + y_max) / 2.0
                elif polygon and len(polygon) >= 4:
                    xs = [p[0] for p in polygon]
                    ys = [p[1] for p in polygon]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    y_center = sum(ys) / float(len(ys))
                else:
                    x_min, x_max, y_min, y_max, y_center = 0.0, 0.0, 0.0, 0.0, 0.0

                if text:
                    normalized.append({
                        "text": text,
                        "score": conf,
                        "x_min": x_min,
                        "x_max": x_max,
                        "y_min": y_min,
                        "y_max": y_max,
                        "y": y_center,
                        "box": [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]],
                    })

        return normalized

    def cluster_rows(
        self,
        boxes: list[dict[str, Any]],
        y_threshold: float | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Cluster boxes into horizontal rows sorted by vertical position, then x_min."""
        if not boxes:
            return []

        thresh = y_threshold if y_threshold is not None else self.row_merge_tolerance_px
        sorted_boxes = sorted(boxes, key=lambda b: b["y"])
        rows: list[list[dict[str, Any]]] = []

        for b in sorted_boxes:
            if not rows or abs(b["y"] - rows[-1][0]["y"]) > thresh:
                rows.append([b])
            else:
                rows[-1].append(b)

        for r in rows:
            r.sort(key=lambda b: b["x_min"])

        return rows

    def _score_table_header(self, row: list[dict[str, Any]], doc_type: DocumentType) -> int:
        """Score a row on how strongly it matches table column headers."""
        # Summary trigger rows can NEVER be table headers
        if self._is_summary_trigger_row(row, doc_type):
            return 0

        row_str = " ".join(b["text"].lower() for b in row)

        # Standard invoice keywords
        has_index = any(
            re.search(r"\b(?:s\.?n\.?o?|sr\.?|sl\.?|item\s*no|#)\b", b["text"], re.IGNORECASE)
            for b in row
        )
        has_desc = any(
            any(k in b["text"].lower() for k in ["description", "particular", "item", "product", "goods", "vigaran", "vivaran"])
            for b in row
        )
        has_qty = any(
            re.search(r"\b(?:qty|quantity|qnty|nos|units?|nang)\b", b["text"], re.IGNORECASE)
            for b in row
        )
        has_rate = any(
            re.search(r"\b(?:rate|price|unit\s*price|mrp|dar)\b", b["text"], re.IGNORECASE)
            for b in row
        )
        has_total = any(
            re.search(r"\b(?:amount|total|value|rakkam)\b", b["text"], re.IGNORECASE)
            for b in row
        )
        has_hsn = any("hsn" in b["text"].lower() or "sac" in b["text"].lower() for b in row)

        invoice_score = 0
        if has_index:
            invoice_score += 2
        if has_desc:
            invoice_score += 3
        if has_qty:
            invoice_score += 3
        if has_rate:
            invoice_score += 3
        if has_total:
            invoice_score += 2
        if has_hsn:
            invoice_score += 1

        if doc_type in [DocumentType.CASH_BOOK, DocumentType.KHATA_LEDGER]:
            has_date = any(k in row_str for k in ["date", "dinank", "dt", "tarikh"])
            has_narration = any(k in row_str for k in ["detail", "particular", "desc", "narration", "head"])
            has_debit = any(k in row_str for k in ["debit", "dr", "paid", "out", "payment", "jama"])
            has_credit = any(k in row_str for k in ["credit", "cr", "received", "in", "receipt", "naam"])
            has_bal = any(k in row_str for k in ["balance", "bal", "baki"])
            has_amt = any(k in row_str for k in ["amount", "rakkam", "total", "rs"])

            ledger_score = 0
            if has_date:
                ledger_score += 2
            if has_narration:
                ledger_score += 3
            if has_debit or has_credit:
                ledger_score += 3
            if has_bal:
                ledger_score += 2
            if has_amt:
                ledger_score += 2

            # Khata Ledgers can have itemized bills or cash book ledgers
            if doc_type == DocumentType.KHATA_LEDGER:
                return max(ledger_score, invoice_score)
            return ledger_score

        # Do not mistake summary rows (like "sub total", "grand total") for table headers
        if "sub total" in row_str or "grand total" in row_str or "cgst" in row_str:
            return 0

        return invoice_score

    def _is_summary_trigger_row(self, row: list[dict[str, Any]], doc_type: DocumentType) -> bool:
        """Check if a row marks the start of the summary/totals section."""
        row_str = " ".join(b["text"].lower() for b in row).strip()

        invoice_triggers = [
            "sub total", "subtotal", "sub-total", "total amount", "total amt",
            "taxable value", "taxable amount", "tax total",
            "cgst", "sgst", "igst", "tax (", "round off", "round-off",
            "grand total", "net total", "net payable", "total payable",
            "balance due", "amount due", "final total", "bill total",
            "amount in words", "amount chargeable", "rupees in words",
            "terms & conditions", "terms and conditions", "terms:",
            "e.&o.e", "e. & o. e.",
        ]
        if any(trig in row_str for trig in invoice_triggers):
            return True

        # Standalone total triggers (e.g. "Total", "Total: 500", "Total Rs. 500", "Total (Rs)")
        if re.search(r"^\s*(?:s\.?no\.?\s*)?total(?:\s*[:.]|\s*\(rs\)?|\s*rs\.?|\s*₹|\s+\d|\s*$)", row_str):
            return True

        if doc_type in [DocumentType.CASH_BOOK, DocumentType.KHATA_LEDGER]:
            ledger_triggers = [
                "closing balance", "closing", "total:", "by balance", "balance c/f", "balance c/d",
                "baki", "jama", "paid", "subtotal", "sub-total", "sub total",
            ]
            if any(trig in row_str for trig in ledger_triggers):
                return True
            if re.search(r"^\s*total(?:\s*[:.]|\s*\(rs\)?|\s*rs\.?|\s*₹|\s+\d|\s*$)", row_str):
                return True
            if re.search(r"^\s*(?:baki|jama|closing|paid)\s*[\(:].*?(?:rs\.?|₹|[\d.]+)", row_str):
                return True

        return False

    def _is_footer_trigger_row(self, row: list[dict[str, Any]]) -> bool:
        """Check if a row marks the beginning of the footer (signatures, stamp, remarks)."""
        row_str = " ".join(b["text"].lower() for b in row)
        footer_triggers = [
            "customer's signature", "authorized signatory", "authorised signatory",
            "for ", "proprietor", "manager signature", "receiver's signature",
        ]
        return any(trig in row_str for trig in footer_triggers)

    def zone(
        self,
        raw_boxes: list[Any],
        doc_type: DocumentType = DocumentType.INVOICE,
        doc_width: float | None = None,
        doc_height: float | None = None,
    ) -> DocumentZones:
        """Partition document bounding boxes into Header, Table, Summary, and Footer zones."""
        boxes = self.standardize_boxes(raw_boxes)
        if not boxes:
            return DocumentZones()

        if doc_width is None or doc_width <= 0:
            doc_width = max(100.0, max(b["x_max"] for b in boxes) * 1.05)
        if doc_height is None or doc_height <= 0:
            doc_height = max(100.0, max(b["y_max"] for b in boxes) * 1.05)

        rows = self.cluster_rows(boxes)
        if not rows:
            return DocumentZones()

        # Step 1: Detect Table Header Row
        header_idx = -1
        max_header_score = 0

        # Scan candidate header rows (typically in top 60% of document)
        max_scan_y = 0.60 * doc_height
        for i, row in enumerate(rows):
            if row[0]["y"] > max_scan_y:
                break
            score = self._score_table_header(row, doc_type)
            if score >= 4 and score > max_header_score:
                max_header_score = score
                header_idx = i

        table_header_row = rows[header_idx] if header_idx != -1 else None

        # Data rows start after header row, or from the first table-like row if headerless
        if header_idx != -1:
            data_start_idx = header_idx + 1
        else:
            # Search for first row that contains line items or ledger items
            data_start_idx = 0
            for i, row in enumerate(rows):
                row_str = " ".join(b["text"].lower() for b in row)
                # Skip vendor, dates, invoice number rows
                if any(k in row_str for k in ["invoice", "date:", "bill no", "gstin", "petty cash", "month:"]):
                    continue
                # If row contains numbers or ledger amounts
                nums = [b for b in row if any(c.isdigit() for c in b["text"])]
                if len(nums) >= 2 or (len(nums) >= 1 and len(row) >= 2):
                    data_start_idx = i
                    break

        # Step 2: Detect Table End / Summary Start
        summary_start_idx = len(rows)
        for i in range(data_start_idx, len(rows)):
            row = rows[i]
            if self._is_summary_trigger_row(row, doc_type):
                summary_start_idx = i
                break

            # Also check if there is an unusually large vertical gap (>150px)
            # followed by summary-like text
            if i > data_start_idx:
                prev_y = rows[i - 1][0]["y"]
                cur_y = row[0]["y"]
                if (cur_y - prev_y) > max(120.0, 0.12 * doc_height):
                    row_str = " ".join(b["text"].lower() for b in row)
                    if any(k in row_str for k in ["total", "amount", "words", "tax", "terms", "rs"]):
                        summary_start_idx = i
                        break

        # Step 3: Partition into Zones
        header_boxes: list[dict[str, Any]] = []
        header_end_idx = header_idx if header_idx != -1 else data_start_idx
        for r in rows[:header_end_idx]:
            header_boxes.extend(r)

        table_rows = rows[data_start_idx:summary_start_idx]

        below_table_rows = rows[summary_start_idx:]
        below_table_boxes: list[dict[str, Any]] = [b for r in below_table_rows for b in r]

        # Step 4: Separate Summary vs Footer
        footer_idx = -1
        for j, r in enumerate(below_table_rows):
            if self._is_footer_trigger_row(r):
                footer_idx = j
                break

        summary_boxes: list[dict[str, Any]] = []
        footer_boxes: list[dict[str, Any]] = []

        if footer_idx != -1:
            for r in below_table_rows[:footer_idx]:
                summary_boxes.extend(r)
            for r in below_table_rows[footer_idx:]:
                footer_boxes.extend(r)
        else:
            summary_boxes = below_table_boxes

        # Step 5: Bilateral Split on Summary Boxes
        boxes_to_split = summary_boxes if summary_boxes else below_table_boxes
        bilateral = self.splitter.split(boxes_to_split, doc_width=doc_width)

        return DocumentZones(
            header_boxes=header_boxes,
            table_header_row=table_header_row,
            table_rows=table_rows,
            summary_boxes=summary_boxes,
            footer_boxes=footer_boxes,
            summary_left_boxes=bilateral.left_boxes,
            summary_right_boxes=bilateral.right_boxes,
            bilateral_summary=bilateral,
        )
