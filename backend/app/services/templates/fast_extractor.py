"""Sub-Second Fast-Path Vision Extractor using Cached Vendor Templates.

When an incoming document matches a stored vendor template (by GSTIN or pHash + vendor name),
this extractor directly slices pre-indexed column channels and applies local OCR (RapidOCR)
without incurring VLM inference latency or running heuristic layout searches.
Enforces deterministic arithmetic validation ($Qty \\times Rate = Total$, $Subtotal + Tax - Discount = GrandTotal$).
If fast-path verification fails, returns None to trigger an automatic fallback to the cold path.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
import uuid

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from backend.app.db.models import VendorTemplateRecord
from backend.app.schemas.document import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    LedgerTransactionItem,
    LineItem,
    verify_document_math,
    verify_ledger_math,
)
from backend.app.services.layout.bilateral_splitter import BilateralBlockSplitter
from backend.app.services.layout.gutter_detector import (
    AdaptiveColumnDetector,
    ColumnInterval,
    ColumnType,
)
from backend.app.services.layout.zoner import DocumentMacroZoner

logger = logging.getLogger(__name__)


class TemplateFastExtractor:
    """Sub-second extractor utilizing pre-indexed spatial templates."""

    def __init__(self):
        self.ocr_engine = RapidOCR()
        self.zoner = DocumentMacroZoner()
        self.column_detector = AdaptiveColumnDetector()
        self.splitter = BilateralBlockSplitter()

    def extract(
        self,
        image_bytes: bytes,
        template: VendorTemplateRecord,
        document_id: str | None = None,
        doc_type: DocumentType = DocumentType.INVOICE,
        precomputed_ocr_results: list[Any] | None = None,
    ) -> DocumentExtractionResponse | None:
        """Execute fast-path extraction using cached column coordinates.

        Returns:
            DocumentExtractionResponse if extraction succeeded and satisfied deterministic math.
            None if parsing or math validation failed (signals fallback to cold path).
        """
        start_time = time.perf_counter()
        doc_id = document_id or str(uuid.uuid4())

        try:
            # 1. Decode image buffer
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                logger.warning("TemplateFastExtractor: Failed to decode image bytes with OpenCV.")
                return None

            h, w = img.shape[:2]

            # 2. Reconstruct cached ColumnIntervals from template table_zone_json
            if not template.table_zone_json:
                logger.warning("TemplateFastExtractor: Template %s has no table_zone_json.", template.id)
                return None

            table_zone_info = json.loads(template.table_zone_json)
            raw_columns = table_zone_info.get("columns", [])
            if not raw_columns:
                logger.warning("TemplateFastExtractor: Template %s has no column definitions.", template.id)
                return None

            columns: list[ColumnInterval] = []
            for c in raw_columns:
                col_type_str = c.get("col_type", "UNKNOWN")
                try:
                    col_type_enum = ColumnType(col_type_str)
                except ValueError:
                    col_type_enum = ColumnType.UNKNOWN

                x_start = float(c["x_start_ratio"]) * w
                x_end = float(c["x_end_ratio"]) * w

                columns.append(
                    ColumnInterval(
                        col_id=int(c.get("col_id", len(columns))),
                        col_type=col_type_enum,
                        x_start=x_start,
                        x_end=x_end,
                        header_text=c.get("header_text"),
                        confidence=1.0,
                    )
                )

            y_table_min = float(table_zone_info.get("y_min_ratio", 0.20)) * h
            y_table_max = float(table_zone_info.get("y_max_ratio", 0.85)) * h

            # 3. High-speed local OCR execution (RapidOCR on CPU: reuse precomputed if passed)
            if precomputed_ocr_results is not None:
                ocr_results = precomputed_ocr_results
            else:
                ocr_results, _ = self.ocr_engine(img)

            if not ocr_results:
                logger.warning("TemplateFastExtractor: RapidOCR returned no text for template fast path.")
                return None

            standard_boxes = self.zoner.standardize_boxes(ocr_results)

            # 4. Partition boxes into functional regions using template coordinates & dynamic summary triggers
            candidate_rows = self.zoner.cluster_rows(standard_boxes, y_threshold=18.0)
            y_table_min_buffered = max(0.0, y_table_min - 0.03 * h)

            header_boxes: list[dict[str, Any]] = []
            table_boxes: list[dict[str, Any]] = []
            summary_boxes: list[dict[str, Any]] = []
            in_summary = False

            for row in candidate_rows:
                row_y = row[0]["y"]
                if row_y < y_table_min_buffered:
                    header_boxes.extend(row)
                else:
                    if not in_summary and self.zoner._is_summary_trigger_row(row, doc_type):
                        in_summary = True
                    if in_summary:
                        summary_boxes.extend(row)
                    else:
                        table_boxes.extend(row)

            # Fallback if no summary trigger was hit
            if not summary_boxes and table_boxes:
                actual_table = [b for b in table_boxes if b["y"] < y_table_max]
                actual_summary = [b for b in table_boxes if b["y"] >= y_table_max]
                table_boxes = actual_table
                summary_boxes = actual_summary

            # 5. Route by column types / document structure
            has_item_cols = any(
                c.col_type in [ColumnType.QUANTITY, ColumnType.RATE]
                for c in columns
            )
            has_ledger_cols = any(
                c.col_type in [ColumnType.DEBIT, ColumnType.CREDIT, ColumnType.BALANCE]
                for c in columns
            )
            is_cash_book = (has_ledger_cols and not has_item_cols) or (
                doc_type == DocumentType.CASH_BOOK and not has_item_cols
            )

            if is_cash_book:
                return self._extract_ledger_fast(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    template=template,
                    header_boxes=header_boxes,
                    table_boxes=table_boxes,
                    columns=columns,
                    start_time=start_time,
                )
            else:
                return self._extract_invoice_fast(
                    doc_id=doc_id,
                    doc_type=doc_type,
                    template=template,
                    img_width=w,
                    header_boxes=header_boxes,
                    table_boxes=table_boxes,
                    summary_boxes=summary_boxes,
                    columns=columns,
                    start_time=start_time,
                )
        except Exception as e:
            logger.warning(
                "TemplateFastExtractor encountered unexpected error for vendor '%s': %s",
                template.vendor_name,
                e,
                exc_info=True,
            )
            return None

    def _extract_invoice_fast(
        self,
        doc_id: str,
        doc_type: DocumentType,
        template: VendorTemplateRecord,
        img_width: int,
        header_boxes: list[dict[str, Any]],
        table_boxes: list[dict[str, Any]],
        summary_boxes: list[dict[str, Any]],
        columns: list[ColumnInterval],
        start_time: float,
    ) -> DocumentExtractionResponse | None:
        """Extract invoice items and totals using cached template geometry."""
        # 1. Extract Header Fields
        vendor_name_val = template.vendor_name
        gstin_val = template.gstin
        invoice_date_val: str | None = None
        invoice_no_val: str | None = None

        header_text = "\n".join(b.get("text", "") for b in header_boxes)
        date_m = re.search(
            r"(?:Date|Dinank|Dated)[:\s]*([0-9]{1,4}[/.-][0-9A-Za-z]{1,3}[/.-][0-9]{2,4})",
            header_text,
            re.IGNORECASE,
        )
        if date_m:
            invoice_date_val = date_m.group(1).strip()

        inv_m = re.search(
            r"(?:Invoice\s*(?:No\.?|#)?|Bill\s*No\.?)[:\s]*([A-Za-z0-9_/-]+)",
            header_text,
            re.IGNORECASE,
        )
        if inv_m:
            invoice_no_val = inv_m.group(1).strip()

        # 2. Extract Table Line Items using cached ColumnIntervals
        table_rows = self.zoner.cluster_rows(table_boxes, y_threshold=20.0)
        raw_items = self.column_detector.parse_invoice_items(table_rows, columns)

        if not raw_items:
            logger.warning("TemplateFastExtractor: 0 line items parsed using template columns.")
            return None

        line_items: list[LineItem] = []
        line_totals: list[float] = []

        for idx, item in enumerate(raw_items, start=1):
            q_val = float(item.get("quantity") or 1.0)
            p_val = float(item.get("unit_price") or 0.0)
            t_val = float(item.get("line_total") or 0.0)

            # Mathematically recover unit price if missing but total and quantity exist
            if p_val == 0.0 and q_val > 0.0 and t_val > 0.0:
                p_val = round(t_val / q_val, 2)

            expected_tot = round(q_val * p_val, 2)
            row_ok = (
                abs(expected_tot - round(t_val, 2)) <= 0.05 * max(t_val, 1.0)
                or abs(expected_tot - round(t_val, 2)) <= 1.0
            )

            li = LineItem(
                row_id=idx,
                page_number=1,
                description=ExtractedField[str](
                    value=item.get("description", ""), confidence=0.96
                ),
                quantity=ExtractedField[float](value=q_val, confidence=0.96),
                unit_price=ExtractedField[float](value=p_val, confidence=0.96),
                line_total=ExtractedField[float](value=t_val, confidence=0.96),
                row_math_valid=row_ok,
                needs_review=not row_ok,
            )
            line_items.append(li)
            line_totals.append(t_val)

        # Enforce strict row math validation: cached layout must satisfy Qty * Rate = Total
        if any(not it.row_math_valid for it in line_items):
            logger.warning(
                "TemplateFastExtractor: Row math failed for '%s'. Layout mismatch detected. Falling back.",
                template.vendor_name,
            )
            return None

        # 3. Extract Summary Totals
        bilateral = self.splitter.split(summary_boxes, doc_width=img_width)
        subtotal_val = bilateral.subtotal
        tax_val = (
            bilateral.tax_amount
            or (bilateral.cgst or 0.0) + (bilateral.sgst or 0.0) + (bilateral.igst or 0.0)
        )
        disc_val = bilateral.discount or 0.0
        grand_total_val = bilateral.grand_total

        # Direct regex scan across summary boxes for missing values
        for b in summary_boxes:
            txt = b.get("text", "").strip()
            lower = txt.lower()
            nums = re.findall(r"(\d+(?:\.\d{1,2})?)", txt)
            if not nums:
                continue
            last_num = float(nums[-1])

            # Subtotal
            if subtotal_val is None and any(k in lower for k in ["subtotal", "sub total", "taxable"]):
                subtotal_val = last_num

            # Tax (Generic GST / VAT / Tax)
            if (
                tax_val == 0.0
                and any(k in lower for k in ["tax", "gst", "vat"])
                and not any(k in lower for k in ["subtotal", "taxable"])
            ):
                tax_val = last_num

            # Discount
            if disc_val == 0.0 and any(k in lower for k in ["discount", "less"]):
                disc_val = last_num

            # Grand Total
            if grand_total_val is None and any(
                k in lower
                for k in ["grand total", "net total", "net payable", "total (rs)", "total amount"]
            ):
                grand_total_val = last_num
            elif grand_total_val is None and re.search(
                r"^\s*total(?:\s*[:.]|\s*\(rs\)?|\s*rs\.?|\s*₹|\s+\d)", lower
            ):
                grand_total_val = last_num

        # In an invoice, at least subtotal or grand total must be explicitly extracted from document text
        if subtotal_val is None and grand_total_val is None:
            logger.warning(
                "TemplateFastExtractor: Neither subtotal nor grand total found in summary for '%s'. Falling back.",
                template.vendor_name,
            )
            return None

        # Infer missing total if one is present
        if subtotal_val is None and line_totals:
            subtotal_val = round(sum(line_totals), 2)
        if grand_total_val is None and subtotal_val is not None:
            grand_total_val = round(subtotal_val + tax_val - disc_val, 2)

        # 4. Deterministic Arithmetic Validation
        math_res = verify_document_math(
            line_totals=line_totals,
            subtotal=subtotal_val,
            tax_amount=tax_val,
            discount_amount=disc_val,
            grand_total=grand_total_val,
            doc_math_tolerance=0.50,
        )

        if not math_res.is_valid:
            logger.warning(
                "TemplateFastExtractor: Deterministic math validation failed for '%s' (%s). Falling back.",
                template.vendor_name,
                math_res.error_details,
            )
            return None

        # 5. Assemble and return fast-path response
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        fields: dict[str, ExtractedField[Any]] = {
            "vendor_name": ExtractedField[str](value=vendor_name_val, confidence=0.98),
            "invoice_date": ExtractedField[str](value=invoice_date_val, confidence=0.95),
            "invoice_number": ExtractedField[str](value=invoice_no_val, confidence=0.95),
            "gstin": ExtractedField[str](value=gstin_val, confidence=0.98),
            "subtotal": ExtractedField[float](value=subtotal_val, confidence=0.96),
            "tax_amount": ExtractedField[float](value=tax_val, confidence=0.96),
            "discount_amount": ExtractedField[float](value=disc_val, confidence=0.96),
            "grand_total": ExtractedField[float](value=grand_total_val, confidence=0.98),
        }

        # Khata ledger specific reconciliation fields
        if doc_type == DocumentType.KHATA_LEDGER:
            jama_val: float | None = None
            baki_val: float | None = None
            for b in summary_boxes:
                txt = b.get("text", "")
                lower = txt.lower()
                nums = re.findall(r"(\d+(?:\.\d{1,2})?)", txt)
                if nums:
                    if any(k in lower for k in ["jama", "paid"]):
                        jama_val = float(nums[-1])
                    if any(k in lower for k in ["baki", "closing"]):
                        baki_val = float(nums[-1])

            if jama_val is not None:
                fields["jama_credit"] = ExtractedField[float](value=jama_val, confidence=0.96)
            if baki_val is not None:
                fields["closing_balance"] = ExtractedField[float](value=baki_val, confidence=0.96)

        return DocumentExtractionResponse(
            document_id=doc_id,
            document_type=doc_type,
            page_count=1,
            pages=[{
                "page_number": 1,
                "confidence": 0.96,
                "items_count": len(line_items),
                "math_valid": True,
            }],
            overall_confidence=0.96,
            status="PROCESSED",
            math_validation=math_res,
            fields=fields,
            line_items=line_items,
            ledger_items=[],
            processing_time_ms=round(latency_ms, 2),
            models_participated=["template_cache", "rapidocr_local"],
            template_matched=True,
            template_vendor=template.vendor_name,
        )

    def _extract_ledger_fast(
        self,
        doc_id: str,
        doc_type: DocumentType,
        template: VendorTemplateRecord,
        header_boxes: list[dict[str, Any]],
        table_boxes: list[dict[str, Any]],
        columns: list[ColumnInterval],
        start_time: float,
    ) -> DocumentExtractionResponse | None:
        """Extract cash book or khata ledger items using cached template geometry."""
        table_rows = self.zoner.cluster_rows(table_boxes, y_threshold=20.0)
        raw_ledger = self.column_detector.parse_cash_book_items(table_rows, columns)

        if not raw_ledger:
            logger.warning("TemplateFastExtractor: 0 ledger items parsed using template columns.")
            return None

        ledger_items: list[LedgerTransactionItem] = []
        for idx, item in enumerate(raw_ledger, start=1):
            lt = LedgerTransactionItem(
                row_id=idx,
                page_number=1,
                entry_date=ExtractedField[str](value=item.get("date", ""), confidence=0.95),
                particulars=ExtractedField[str](value=item.get("particulars", ""), confidence=0.95),
                voucher_no=ExtractedField[str](value=item.get("voucher_no")) if item.get("voucher_no") else None,
                cash_out_debit=ExtractedField[float](value=float(item.get("cash_out_debit") or 0.0), confidence=0.95),
                cash_in_credit=ExtractedField[float](value=float(item.get("cash_in_credit") or 0.0), confidence=0.95),
                running_balance=ExtractedField[float](value=float(item.get("running_balance") or 0.0), confidence=0.95),
                balance_math_valid=True,
                needs_review=False,
            )
            ledger_items.append(lt)

        # Validate ledger continuity arithmetic
        math_res = verify_ledger_math(ledger_items)
        if not math_res.is_valid:
            logger.warning(
                "TemplateFastExtractor: Ledger math validation failed for '%s': %s",
                template.vendor_name,
                math_res.error_details,
            )
            return None

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return DocumentExtractionResponse(
            document_id=doc_id,
            document_type=doc_type,
            page_count=1,
            pages=[{
                "page_number": 1,
                "confidence": 0.95,
                "items_count": len(ledger_items),
                "math_valid": True,
            }],
            overall_confidence=0.95,
            status="PROCESSED",
            math_validation=math_res,
            fields={
                "book_title": ExtractedField[str](value=template.vendor_name, confidence=0.98),
            },
            line_items=[],
            ledger_items=ledger_items,
            processing_time_ms=round(latency_ms, 2),
            models_participated=["template_cache", "rapidocr_local"],
            template_matched=True,
            template_vendor=template.vendor_name,
        )


# Global singleton instance
template_fast_extractor = TemplateFastExtractor()
