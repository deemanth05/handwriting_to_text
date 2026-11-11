"""Model D / Local Engine: Surya Multilingual OCR Extractor.

Integrates Vik Paruchuri's Surya OCR (https://github.com/datalab-to/surya)
running locally on CPU/CUDA for multilingual & handwriting line extraction.
Extracts bounding boxes, text lines, and table rows with offline resilience.
"""

from itertools import combinations, permutations
import io
import json
import logging
import re
import time
from typing import Any

import numpy as np
from PIL import Image

from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput

logger = logging.getLogger(__name__)


def parse_numeric(text: str) -> float:
    """Parse string to float, normalizing punctuation quirks like 23:60 -> 23.60, commas in 1,200.00."""
    if not text:
        return 0.0
    cleaned = text.strip()
    # Strip currency indicators
    cleaned = re.sub(r"[₹$£€]|rs\.?|inr", "", cleaned, flags=re.IGNORECASE).strip()
    # Replace colon or semicolon between digits with dot (e.g., 23:60 -> 23.60)
    cleaned = re.sub(r"(?<=\d)[:;](?=\d)", ".", cleaned)
    # If commas are used as thousand separators (e.g. 1,200.00 or 1,200)
    if re.search(r"\d+,\d{3}", cleaned):
        cleaned = cleaned.replace(",", "")
    else:
        # If comma is used as decimal separator (e.g. 23,60)
        cleaned = re.sub(r"(?<=\d),(?=\d{1,2}$)", ".", cleaned)
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return 0.0


class SuryaLocalExtractor(BaseVisionExtractor):
    """Local multilingual document OCR engine powered by Surya."""

    _det_model = None
    _det_processor = None
    _rec_model = None
    _rec_processor = None
    _det_predictor = None
    _rec_predictor = None

    def __init__(
        self,
        name: str = "surya_local",
        model_id: str = "surya-ocr",
        langs: list[str] | None = None,
    ):
        super().__init__(name=name, model_id=model_id)
        self.langs = langs or ["en", "hi"]

    @classmethod
    def _get_models(cls):
        """Lazy-load Surya detection and recognition models as singletons."""
        if cls._rec_model is None or cls._det_model is None:
            try:
                from surya.model.detection.model import (
                    load_model as load_det_model,
                    load_processor as load_det_processor,
                )
                from surya.model.recognition.model import (
                    load_model as load_rec_model,
                    load_processor as load_rec_processor,
                )

                cls._det_processor, cls._det_model = load_det_processor(), load_det_model()
                cls._rec_model, cls._rec_processor = load_rec_model(), load_rec_processor()
            except Exception as e:
                logger.error(f"Failed to load Surya models: {e}")
                raise

        return cls._det_processor, cls._det_model, cls._rec_model, cls._rec_processor

    def _cluster_rows(self, text_lines: list[Any], y_threshold: float = 25.0) -> list[list[dict[str, Any]]]:
        """Cluster Surya text lines into horizontal rows sorted top-to-bottom and left-to-right."""
        items: list[dict[str, Any]] = []
        for line in text_lines:
            text = getattr(line, "text", "")
            if isinstance(line, dict):
                text = line.get("text", "")
                conf = float(line.get("confidence", 0.8) or 0.8)
                bbox = line.get("bbox")
                polygon = line.get("polygon")
            else:
                conf = float(getattr(line, "confidence", 0.8) or 0.8)
                bbox = getattr(line, "bbox", None)
                polygon = getattr(line, "polygon", None)

            text = text.strip()
            if not text:
                continue

            if bbox and len(bbox) == 4:
                x_min, y_min, x_max, y_max = bbox
                y_center = (y_min + y_max) / 2.0
            elif polygon and len(polygon) >= 4:
                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                x_min, x_max = min(xs), max(xs)
                y_center = sum(ys) / float(len(ys))
            else:
                x_min, x_max, y_center = 0.0, 0.0, 0.0

            items.append({
                "text": text,
                "score": conf,
                "y": y_center,
                "x_min": x_min,
                "x_max": x_max,
            })

        items.sort(key=lambda it: it["y"])
        rows: list[list[dict[str, Any]]] = []
        for it in items:
            if not rows or abs(it["y"] - rows[-1][0]["y"]) > y_threshold:
                rows.append([it])
            else:
                rows[-1].append(it)

        for r in rows:
            r.sort(key=lambda it: it["x_min"])

        return rows

    def _parse_cash_book(self, rows: list[list[dict[str, Any]]], raw_lines: list[str]) -> dict[str, Any]:
        """Parse rows into Cash Book ledger schema."""
        book_title = "Petty Cash Book"
        period = None
        page_no = None

        for r in rows[:4]:
            text = " ".join(b["text"] for b in r)
            if "petty cash" in text.lower():
                book_title = "Petty Cash Book"
            month_match = re.search(r"Month[:\s]*([A-Za-z0-9\s]+)", text, re.IGNORECASE)
            if month_match:
                period = f"Month: {month_match.group(1).strip()}"
            page_match = re.search(r"Page\s*No[.:\s]*(\d+)", text, re.IGNORECASE)
            if page_match:
                page_no = page_match.group(1).strip()

        max_x = 1000.0
        all_xs = [b["x_max"] for r in rows for b in r]
        if all_xs:
            max_x = max(all_xs)

        header_idx = -1
        col_positions: dict[str, float] = {}
        for i, r in enumerate(rows):
            row_text = " ".join(b["text"].lower() for b in r)
            has_desc = any(k in row_text for k in ["detail", "particular", "desc", "narration", "item"])
            has_amt = any(k in row_text for k in ["bal", "out", "in", "debit", "credit", "amount", "paid", "received", "dr", "cr"])
            if (has_desc and has_amt) or ("date" in row_text and has_amt):
                header_idx = i
                for b in r:
                    txt = b["text"].lower()
                    if "date" in txt or "dinank" in txt or "dt" in txt:
                        col_positions["date"] = b["x_min"]
                    elif "detail" in txt or "particular" in txt or "desc" in txt:
                        col_positions["details"] = b["x_min"]
                    elif "out" in txt or "debit" in txt or "dr" in txt or "paid" in txt or "payment" in txt:
                        col_positions["out"] = b["x_min"]
                    elif "in" in txt or "credit" in txt or "cr" in txt or "receipt" in txt or "received" in txt:
                        col_positions["in"] = b["x_min"]
                    elif "balance" in txt or "bal" in txt or "baki" in txt:
                        col_positions["balance"] = b["x_min"]
                break

        d_x = col_positions.get("details", max_x * 0.23)
        o_x = col_positions.get("out", max_x * 0.55)
        i_x = col_positions.get("in", max_x * 0.71)
        b_x = col_positions.get("balance", max_x * 0.86)
        date_x = col_positions.get("date", max_x * 0.08)

        split_date_desc = (date_x + d_x) / 2
        split_desc_out = (d_x + o_x) / 2
        split_out_in = (o_x + i_x) / 2
        split_in_bal = (i_x + b_x) / 2

        data_rows = rows[header_idx + 1 :] if header_idx != -1 else rows

        ledger_items: list[dict[str, Any]] = []
        opening_balance: float | None = None
        closing_balance: float | None = None

        for r in data_rows:
            row_str = " ".join(b["text"].lower() for b in r)
            if any(k in row_str for k in ["page no", "petty cash", "month:"]):
                continue
            if ("detail" in row_str or "particular" in row_str) and ("out" in row_str or "debit" in row_str or "balance" in row_str or "in" in row_str or "credit" in row_str):
                continue

            date_val: str | None = None
            particulars_parts: list[str] = []
            out_val: float = 0.0
            in_val: float = 0.0
            bal_val: float = 0.0

            for b in r:
                t = b["text"].strip()
                x = b["x_min"]

                if x < split_date_desc:
                    if re.match(r"^\d{1,2}[/-]\d{1,2}", t):
                        date_val = t
                    else:
                        particulars_parts.append(t)
                elif split_date_desc <= x < split_desc_out:
                    particulars_parts.append(t)
                elif split_desc_out <= x < split_out_in:
                    num = parse_numeric(t)
                    if num > 0:
                        out_val = num
                elif split_out_in <= x < split_in_bal:
                    num = parse_numeric(t)
                    if num > 0:
                        in_val = num
                else:
                    num = parse_numeric(t)
                    if num > 0:
                        bal_val = num

            particulars = " ".join(particulars_parts).strip()
            if not particulars and out_val == 0.0 and in_val == 0.0 and bal_val == 0.0:
                continue

            if "opening balance" in particulars.lower() and in_val > 0 and bal_val == 0.0:
                bal_val = in_val

            if opening_balance is None and "opening" in particulars.lower():
                opening_balance = in_val or bal_val

            if bal_val > 0:
                closing_balance = bal_val

            ledger_items.append({
                "entry_date": date_val or "",
                "particulars": particulars,
                "voucher_no": None,
                "cash_out_debit": out_val,
                "cash_in_credit": in_val,
                "running_balance": bal_val,
            })

        return {
            "book_title": book_title,
            "period": period,
            "page_no": page_no,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "ledger_items": ledger_items,
        }

    def _parse_invoice(self, rows: list[list[dict[str, Any]]], raw_lines: list[str]) -> dict[str, Any]:
        """Parse rows into canonical invoice schema."""
        vendor_name = None
        invoice_date = None
        invoice_number = None
        subtotal = None
        tax_amount = None
        discount_amount = None
        grand_total = None

        full_text = "\n".join(raw_lines)

        if raw_lines:
            vendor_name = raw_lines[0]

        date_m = re.search(r"(?:Date|Dinank)[:\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", full_text, re.IGNORECASE)
        if date_m:
            invoice_date = date_m.group(1).strip()

        inv_m = re.search(r"(?:Invoice\s*#?|Bill\s*No)[:\s]*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
        if inv_m:
            invoice_number = inv_m.group(1).strip()

        sub_m = re.search(r"(?:Subtotal|Total\s*Amt)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
        if sub_m:
            subtotal = parse_numeric(sub_m.group(1))

        tax_m = re.search(r"(?:Tax|GST)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
        if tax_m:
            tax_amount = parse_numeric(tax_m.group(1))

        disc_m = re.search(r"(?:Discount)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
        if disc_m:
            discount_amount = parse_numeric(disc_m.group(1))

        grand_m = re.search(r"(?:Grand\s*Total|Net\s*Total|Total)[:\s]*Rs\.?\s*([\d.]+)", full_text, re.IGNORECASE)
        if grand_m:
            grand_total = parse_numeric(grand_m.group(1))

        line_items: list[dict[str, Any]] = []
        for r in rows:
            line_str = " ".join(b["text"] for b in r)
            if any(k in line_str.lower() for k in ["subtotal", "grand total", "discount", "tax (", "gstin", "invoice #", "paid&"]):
                continue

            num_boxes: list[tuple[float, dict[str, Any]]] = []
            text_boxes: list[dict[str, Any]] = []
            for b in r:
                t = b["text"].strip()
                t_clean = re.sub(r"[₹$£€]|rs\.?|inr", "", t, flags=re.IGNORECASE).strip()
                if re.match(r"^\d+(?:[.,:]\d+)?$", t_clean) or re.match(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$", t_clean):
                    val = parse_numeric(t)
                    if val > 0:
                        num_boxes.append((val, b))
                    else:
                        text_boxes.append(b)
                else:
                    text_boxes.append(b)

            if text_boxes and num_boxes:
                min_num_x = min(nb["x_min"] for _, nb in num_boxes)
                desc_parts = [tb["text"] for tb in text_boxes if tb["x_min"] < min_num_x]
                if not desc_parts:
                    desc_parts = [tb["text"] for tb in text_boxes]
                desc = " ".join(desc_parts).strip()
                if desc.lower() in ["ite m description", "rate", "qty", "total (rs)", "rakkam", "vigaran", "description", "item"]:
                    continue

                numbers = [val for val, _ in num_boxes]
                assigned = False
                if len(numbers) >= 3:
                    candidate_triplets = []
                    if len(numbers) == 3:
                        candidate_triplets.append(numbers)
                    else:
                        candidate_triplets.append(numbers[-3:])
                        for comb in combinations(numbers, 3):
                            comb_list = list(comb)
                            if comb_list != numbers[-3:]:
                                candidate_triplets.append(comb_list)

                    for triplet in candidate_triplets:
                        valid_perms = []
                        for q_cand, p_cand, t_cand in permutations(triplet, 3):
                            if q_cand > 0 and p_cand > 0 and abs(q_cand * p_cand - t_cand) <= 0.05:
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

                            qty, unit_p, tot = best
                            assigned = True
                            break

                if not assigned:
                    if len(numbers) >= 3:
                        qty = numbers[-3]
                        unit_p = numbers[-2]
                        tot = numbers[-1]
                    elif len(numbers) == 2:
                        unit_p = numbers[-2]
                        tot = numbers[-1]
                        qty = round(tot / unit_p, 2) if unit_p > 0 else 1.0
                    else:
                        tot = numbers[-1]
                        unit_p = tot
                        qty = 1.0

                line_items.append({
                    "description": desc,
                    "quantity": qty,
                    "unit_price": unit_p,
                    "line_total": tot,
                })

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

    def _parse_general(self, rows: list[list[dict[str, Any]]], raw_lines: list[str]) -> dict[str, Any]:
        """Generic fallback extractor."""
        return {
            "document_title": raw_lines[0] if raw_lines else "Untitled Document",
            "lines": raw_lines,
        }

    async def extract(self, image_bytes: bytes, doc_type: DocumentType) -> RawModelOutput:
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
                from surya.detection import DetectionPredictor

                if self.__class__._rec_predictor is None or self.__class__._det_predictor is None:
                    self.__class__._det_predictor = DetectionPredictor()
                    self.__class__._rec_predictor = RecognitionPredictor()

                predictions = self.__class__._rec_predictor(
                    [pil_image],
                    [self.langs],
                    self.__class__._det_predictor,
                )
            except (ImportError, AttributeError):
                from surya.ocr import run_ocr
                det_processor, det_model, rec_model, rec_processor = self._get_models()

                # Run Surya OCR
                predictions = run_ocr(
                    [pil_image],
                    [self.langs],
                    det_model,
                    det_processor,
                    rec_model,
                    rec_processor,
                )

            text_lines = predictions[0].text_lines if predictions else []
            raw_lines = [line.text.strip() for line in text_lines if getattr(line, "text", "").strip()]
            raw_text = "\n".join(raw_lines)

            # Cluster text lines into spatial rows
            rows = self._cluster_rows(text_lines)

            # Schema parsing
            if doc_type in [DocumentType.CASH_BOOK, DocumentType.KHATA_LEDGER]:
                parsed_json = self._parse_cash_book(rows, raw_lines)
            elif doc_type == DocumentType.INVOICE:
                parsed_json = self._parse_invoice(rows, raw_lines)
            else:
                parsed_json = self._parse_general(rows, raw_lines)

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
