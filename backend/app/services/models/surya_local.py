"""Model D / Local Engine: Surya Multilingual OCR Extractor.

Integrates Vik Paruchuri's Surya OCR (https://github.com/datalab-to/surya)
running locally on CPU/CUDA for multilingual & handwriting line extraction.
Extracts bounding boxes, text lines, and table rows with offline resilience.
Leverages DocumentMacroZoner, AdaptiveColumnDetector, BilateralBlockSplitter,
and optional SuryaTableAdapter.
"""

from __future__ import annotations

import html
import io
import json
import logging
import re
import time
from typing import Any

import numpy as np
from PIL import Image

from backend.app.schemas.document import DocumentType
from backend.app.services.layout.bilateral_splitter import (
    BilateralBlockSplitter,
    parse_numeric,
)
from backend.app.services.layout.gutter_detector import AdaptiveColumnDetector
from backend.app.services.layout.surya_table_adapter import SuryaTableAdapter
from backend.app.services.layout.zoner import DocumentMacroZoner, DocumentZones
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput

logger = logging.getLogger(__name__)


class SuryaLocalExtractor(BaseVisionExtractor):
    """Local multilingual document OCR engine powered by Surya."""

    _layout_predictor = None
    _rec_predictor = None

    def __init__(
        self,
        name: str = "surya_local",
        model_id: str = "surya-ocr",
        langs: list[str] | None = None,
    ):
        super().__init__(name=name, model_id=model_id)
        self.langs = langs or ["en", "hi"]
        self.zoner = DocumentMacroZoner()
        self.column_detector = AdaptiveColumnDetector()
        self.splitter = BilateralBlockSplitter()
        self.table_adapter = SuryaTableAdapter()

    def _cluster_rows(self, text_lines: list[Any], y_threshold: float = 25.0) -> list[list[dict[str, Any]]]:
        """Cluster Surya text lines into horizontal rows sorted top-to-bottom and left-to-right."""
        return self.zoner.cluster_rows(self.zoner.standardize_boxes(text_lines), y_threshold=y_threshold)

    def _parse_cash_book(
        self,
        rows: list[list[dict[str, Any]]],
        raw_lines: list[str],
        zones: DocumentZones | None = None,
        doc_width: float | None = None,
    ) -> dict[str, Any]:
        """Parse rows into Cash Book ledger schema."""
        book_title = "Petty Cash Book"
        period = None
        page_no = None

        header_search_boxes = zones.header_boxes if zones and zones.header_boxes else [b for r in rows[:4] for b in r]
        for b in header_search_boxes:
            txt = b.get("text", "")
            if "petty cash" in txt.lower():
                book_title = "Petty Cash Book"
            month_match = re.search(r"Month[:\s]*([A-Za-z0-9\s]+)", txt, re.IGNORECASE)
            if month_match:
                period = f"Month: {month_match.group(1).strip()}"
            page_match = re.search(r"Page\s*No[.:\s]*(\d+)", txt, re.IGNORECASE)
            if page_match:
                page_no = page_match.group(1).strip()

        if not period or not page_no:
            for l in raw_lines[:5]:
                month_match = re.search(r"Month[:\s]*([A-Za-z0-9\s]+)", l, re.IGNORECASE)
                if month_match and not period:
                    period = f"Month: {month_match.group(1).strip()}"
                page_match = re.search(r"Page\s*No[.:\s]*(\d+)", l, re.IGNORECASE)
                if page_match and not page_no:
                    page_no = page_match.group(1).strip()

        if zones and zones.table_rows:
            table_rows = zones.table_rows
            table_header_row = zones.table_header_row
        else:
            boxes = [b for r in rows for b in r]
            constructed_zones = self.zoner.zone(boxes, doc_type=DocumentType.CASH_BOOK, doc_width=doc_width)
            table_rows = constructed_zones.table_rows if constructed_zones.table_rows else rows
            table_header_row = constructed_zones.table_header_row

        columns = self.column_detector.detect_columns(
            table_rows=table_rows,
            table_header_row=table_header_row,
            doc_width=doc_width,
            doc_type=DocumentType.CASH_BOOK,
        )

        ledger_items = self.column_detector.parse_cash_book_items(table_rows, columns)

        opening_balance: float | None = None
        closing_balance: float | None = None

        for item in ledger_items:
            part = item["particulars"].lower()
            if "opening" in part and opening_balance is None:
                opening_balance = item["running_balance"] or item["cash_in_credit"]

            if item["running_balance"] > 0:
                closing_balance = item["running_balance"]

        return {
            "book_title": book_title,
            "period": period,
            "page_no": page_no,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "ledger_items": ledger_items,
        }

    def _parse_invoice(
        self,
        rows: list[list[dict[str, Any]]],
        raw_lines: list[str],
        zones: DocumentZones | None = None,
        doc_width: float | None = None,
    ) -> dict[str, Any]:
        """Parse rows into canonical invoice schema using macro-zones and adaptive gutters."""
        vendor_name = None
        invoice_date = None
        invoice_number = None
        subtotal = None
        tax_amount = None
        discount_amount = None
        grand_total = None

        full_text = "\n".join(raw_lines)

        if zones and zones.header_boxes:
            for b in zones.header_boxes:
                t = b["text"].strip()
                if len(t) > 3 and not any(k in t.lower() for k in ["gstin", "invoice", "date", "bill no", "phone"]):
                    vendor_name = t
                    break

        if not vendor_name and raw_lines:
            vendor_name = raw_lines[0]

        date_m = re.search(r"(?:Date|Dinank)[:\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", full_text, re.IGNORECASE)
        if date_m:
            invoice_date = date_m.group(1).strip()

        inv_m = re.search(r"(?:Invoice\s*(?:No\.?|#)?|Bill\s*No\.?)[:\s]*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
        if inv_m:
            invoice_number = inv_m.group(1).strip()

        # Table rows and header row determination
        if not zones:
            boxes = [b for r in rows for b in r]
            zones = self.zoner.zone(boxes, doc_type=DocumentType.INVOICE, doc_width=doc_width)

        table_rows = zones.table_rows if zones.table_rows else rows
        table_header_row = zones.table_header_row
        columns = self.column_detector.detect_columns(
            table_rows=table_rows,
            table_header_row=table_header_row,
            doc_width=doc_width,
            doc_type=DocumentType.INVOICE,
        )
        line_items = self.column_detector.parse_invoice_items(table_rows, columns)

        if zones.bilateral_summary:
            bs = zones.bilateral_summary
            subtotal = bs.subtotal
            discount_amount = bs.discount
            tax_amount = bs.tax_amount
            grand_total = bs.grand_total

        if subtotal is None:
            sub_m = re.search(r"(?:Subtotal|Total\s*Amt)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
            if sub_m:
                subtotal = parse_numeric(sub_m.group(1))

        if tax_amount is None:
            tax_m = re.search(r"(?:Tax|GST)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
            if tax_m:
                tax_amount = parse_numeric(tax_m.group(1))

        if discount_amount is None:
            disc_m = re.search(r"(?:Discount)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
            if disc_m:
                discount_amount = parse_numeric(disc_m.group(1))

        if grand_total is None:
            grand_m = re.search(r"(?:Grand\s*Total|Net\s*Total|Total)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
            if grand_m:
                grand_total = parse_numeric(grand_m.group(1))

        return {
            "vendor_name": vendor_name,
            "invoice_date": invoice_date,
            "invoice_number": invoice_number,
            "line_items": line_items,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "discount_amount": discount_amount,
            "grand_total": grand_total,
        }

    def _parse_khata(
        self,
        rows: list[list[dict[str, Any]]],
        raw_lines: list[str],
        zones: DocumentZones | None = None,
        doc_width: float | None = None,
    ) -> dict[str, Any]:
        """Parse rows into Khata ledger schema."""
        full_text = "\n".join(raw_lines)
        customer_name = None
        doc_date = None

        cust_m = re.search(r"(?:Grahak\s*Naam|Customer)[:\s]*([^\n]+)", full_text, re.IGNORECASE)
        if cust_m:
            customer_name = cust_m.group(1).strip()

        date_m = re.search(r"(?:Dinank|Date)[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", full_text, re.IGNORECASE)
        if date_m:
            doc_date = date_m.group(1).strip()

        inv_data = self._parse_invoice(rows, raw_lines, zones=zones, doc_width=doc_width)

        jama_m = re.search(r"(?:Jama|Paid)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
        jama_credit = parse_numeric(jama_m.group(1)) if jama_m else None

        naam_m = re.search(r"(?:Baki|Closing|Naam)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
        closing_bal = parse_numeric(naam_m.group(1)) if naam_m else None

        return {
            "customer_name": customer_name,
            "document_date": doc_date,
            "account_number": None,
            "line_items": inv_data["line_items"],
            "jama_credit": jama_credit,
            "naam_debit": None,
            "subtotal": inv_data["subtotal"],
            "grand_total": closing_bal or inv_data["grand_total"],
        }

    def _parse_prescription(
        self,
        rows: list[list[dict[str, Any]]],
        raw_lines: list[str],
        zones: DocumentZones | None = None,
    ) -> dict[str, Any]:
        """Parse rows into Prescription schema."""
        full_text = "\n".join(raw_lines)
        clinic_doctor = raw_lines[0] if raw_lines else None
        patient_name = None
        doc_date = None

        pat_m = re.search(r"Patient[:\s]*([^\n|I]+)", full_text, re.IGNORECASE)
        if pat_m:
            patient_name = pat_m.group(1).strip()

        date_m = re.search(r"Date[:\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", full_text, re.IGNORECASE)
        if date_m:
            doc_date = date_m.group(1).strip()

        line_items = []
        for line in raw_lines:
            med_m = re.search(r"^\d+\.\s*(.+)", line)
            if med_m:
                med_desc = med_m.group(1).strip()
                line_items.append({
                    "description": med_desc,
                    "quantity": 1.0,
                    "dosage": "1-0-1",
                    "duration": "5 days",
                    "unit_price": None,
                    "line_total": None,
                })

        return {
            "clinic_or_doctor_name": clinic_doctor,
            "patient_name": patient_name,
            "document_date": doc_date,
            "prescription_number": None,
            "line_items": line_items,
        }

    def _parse_general(self, rows: list[list[dict[str, Any]]], raw_lines: list[str]) -> dict[str, Any]:
        """Generic fallback extractor."""
        return {
            "document_title": raw_lines[0] if raw_lines else "Untitled Document",
            "lines": raw_lines,
        }

    async def extract(self, image_bytes: bytes, doc_type: DocumentType = DocumentType.INVOICE) -> RawModelOutput:
        """Run Surya OCR locally on image bytes and parse into structured JSON."""
        t0 = time.perf_counter()
        if not image_bytes:
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                parsed_json={},
                latency_ms=0.0,
                status="ERROR",
                error="Empty image buffer provided",
            )

        try:
            pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                parsed_json={},
                latency_ms=(time.perf_counter() - t0) * 1000,
                status="ERROR",
                error=f"Failed to decode image: {e}",
            )

        try:
            try:
                from surya.recognition import RecognitionPredictor
                from surya.layout import LayoutPredictor

                if self.__class__._rec_predictor is None or self.__class__._layout_predictor is None:
                    self.__class__._layout_predictor = LayoutPredictor()
                    self.__class__._rec_predictor = RecognitionPredictor()

                layout_results = self.__class__._layout_predictor([pil_image])
                predictions = self.__class__._rec_predictor([pil_image], layout_results=layout_results)
            except Exception as e_layout:
                logger.warning("Surya layout predictor failed, falling back to direct recognition: %s", e_layout)
                from surya.recognition import RecognitionPredictor

                if self.__class__._rec_predictor is None:
                    self.__class__._rec_predictor = RecognitionPredictor()

                predictions = self.__class__._rec_predictor([pil_image])

            text_lines = []
            if predictions:
                pred = predictions[0]
                if hasattr(pred, "text_lines"):
                    text_lines = pred.text_lines
                elif hasattr(pred, "blocks"):
                    text_lines = [b for b in pred.blocks if not getattr(b, "skipped", False)]

            raw_lines: list[str] = []
            for line in text_lines:
                txt = getattr(line, "text", line.get("text", "") if isinstance(line, dict) else "")
                if not txt and hasattr(line, "html"):
                    txt = re.sub(r"<[^>]+>", "", getattr(line, "html", ""))
                    txt = html.unescape(txt)
                elif not txt and isinstance(line, dict) and "html" in line:
                    txt = re.sub(r"<[^>]+>", "", line["html"])
                    txt = html.unescape(txt)
                txt = str(txt).strip()
                if txt:
                    raw_lines.append(txt)

            raw_text = "\n".join(raw_lines)

            # Hierarchical Macro-Zoning
            zones = self.zoner.zone(text_lines, doc_type=doc_type, doc_width=pil_image.width, doc_height=pil_image.height)

            # Optional deep table recognition if enabled
            deep_table_items = None
            if self.table_adapter.enabled:
                table_res = self.table_adapter.predict_table(pil_image)
                if table_res:
                    grid = self.table_adapter.map_cells_to_grid(table_res, self.zoner.standardize_boxes(text_lines))
                    deep_table_items = self.table_adapter.parse_grid_to_line_items(grid, doc_type=doc_type)

            # Schema parsing
            if doc_type == DocumentType.CASH_BOOK:
                parsed_json = self._parse_cash_book(zones.table_rows, raw_lines, zones=zones, doc_width=pil_image.width)
            elif doc_type == DocumentType.KHATA_LEDGER:
                parsed_json = self._parse_khata(zones.table_rows, raw_lines, zones=zones, doc_width=pil_image.width)
            elif doc_type == DocumentType.PRESCRIPTION:
                parsed_json = self._parse_prescription(zones.table_rows, raw_lines, zones=zones)
            elif doc_type == DocumentType.INVOICE:
                parsed_json = self._parse_invoice(zones.table_rows, raw_lines, zones=zones, doc_width=pil_image.width)
                if deep_table_items:
                    parsed_json["line_items"] = deep_table_items
            else:
                parsed_json = self._parse_general(zones.table_rows, raw_lines)

            duration = (time.perf_counter() - t0) * 1000
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text=raw_text,
                parsed_json=parsed_json,
                latency_ms=round(duration, 2),
                status="SUCCESS",
            )

        except Exception as exc:
            duration = (time.perf_counter() - t0) * 1000
            logger.exception("Surya OCR extraction failed")
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                parsed_json={},
                latency_ms=round(duration, 2),
                status="ERROR",
                error=str(exc),
            )
