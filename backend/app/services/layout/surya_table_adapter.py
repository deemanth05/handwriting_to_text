"""Adapter for Surya TableRecPredictor and Deep Visual Table Recognition.

Provides zero-heuristic deep visual table polygon extraction when deep visual parsing
is enabled via `config.ENABLE_SURYA_TABLE_REC = True`, with graceful degradation
to fast geometric layout when disabled or offline.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from PIL import Image

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.layout.bilateral_splitter import parse_numeric

logger = logging.getLogger(__name__)


class SuryaTableAdapter:
    """Enterprise adapter for Surya Deep-Learning Table Recognition."""

    _table_predictor = None

    def __init__(self):
        self.enabled = getattr(settings, "ENABLE_SURYA_TABLE_REC", False)

    @classmethod
    def is_available(cls) -> bool:
        """Check whether Surya table recognition dependencies are installed."""
        try:
            from surya.table_rec import TableRecPredictor
            return True
        except (ImportError, Exception):
            return False

    @classmethod
    def _get_predictor(cls):
        """Lazy-load the Surya TableRecPredictor singleton."""
        if cls._table_predictor is None:
            try:
                from surya.table_rec import TableRecPredictor
                cls._table_predictor = TableRecPredictor()
            except Exception as e:
                logger.warning(f"Could not initialize Surya TableRecPredictor: {e}")
                raise
        return cls._table_predictor

    def predict_table(self, pil_image: Image.Image) -> Any | None:
        """Run Surya deep learning table extraction on a PIL Image if enabled."""
        if not self.enabled:
            return None

        try:
            predictor = self._get_predictor()
            results = predictor([pil_image])
            return results[0] if results else None
        except Exception as e:
            logger.warning(f"Surya TableRec inference failed or models unavailable, using fast fallback: {e}")
            return None

    def _get_cell_bbox(self, cell: Any) -> list[float] | None:
        """Extract canonical [x_min, y_min, x_max, y_max] from TableCell object or dict."""
        bbox = getattr(cell, "bbox", None)
        if bbox is not None:
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                return [float(x) for x in bbox]

        polygon = getattr(cell, "polygon", None)
        if polygon and len(polygon) >= 4:
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]

        if isinstance(cell, dict):
            if "bbox" in cell and len(cell["bbox"]) == 4:
                return [float(x) for x in cell["bbox"]]
            if "polygon" in cell and len(cell["polygon"]) >= 4:
                xs = [p[0] for p in cell["polygon"]]
                ys = [p[1] for p in cell["polygon"]]
                return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]

        return None

    def map_cells_to_grid(
        self,
        table_result: Any,
        text_lines: list[dict[str, Any]],
    ) -> list[list[str]]:
        """Map OCR text boxes into the 2D cell grid predicted by Surya TableRec."""
        if not table_result or not getattr(table_result, "cells", None):
            return []

        cells = table_result.cells
        max_row = max((c.row_id for c in cells), default=0)
        max_col = max((c.col_id for c in cells), default=0)

        # Initialize grid
        grid: list[list[list[str]]] = [[[] for _ in range(max_col + 1)] for _ in range(max_row + 1)]

        for box in text_lines:
            b_x = (box["x_min"] + box["x_max"]) / 2.0
            b_y = box.get("y", (box["y_min"] + box["y_max"]) / 2.0 if "y_min" in box else 0.0)

            # Find containing cell
            matched = False
            for cell in cells:
                c_bbox = self._get_cell_bbox(cell)
                if c_bbox and len(c_bbox) == 4:
                    if c_bbox[0] <= b_x <= c_bbox[2] and c_bbox[1] <= b_y <= c_bbox[3]:
                        grid[cell.row_id][cell.col_id].append(box["text"])
                        matched = True
                        break

            if not matched and cells:
                # Assign to nearest cell center
                def _dist(c: Any) -> float:
                    bbox = self._get_cell_bbox(c)
                    if bbox and len(bbox) == 4:
                        cx = (bbox[0] + bbox[2]) / 2.0
                        cy = (bbox[1] + bbox[3]) / 2.0
                        return (cx - b_x) ** 2 + (cy - b_y) ** 2
                    return float("inf")

                best_cell = min(cells, key=_dist)
                grid[best_cell.row_id][best_cell.col_id].append(box["text"])

        # Flatten string lists
        flat_grid: list[list[str]] = [
            [" ".join(cell_texts).strip() for cell_texts in row]
            for row in grid
        ]
        return flat_grid

    def parse_grid_to_line_items(
        self,
        grid: list[list[str]],
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> list[dict[str, Any]]:
        """Convert a 2D text matrix into canonical line items."""
        if not grid or len(grid) < 2:
            return []

        header_row = [c.lower() for c in grid[0]]
        data_rows = grid[1:]

        # Map column positions from header
        desc_col = -1
        qty_col = -1
        rate_col = -1
        total_col = -1

        for c_idx, h_text in enumerate(header_row):
            if any(k in h_text for k in ["description", "particular", "item", "product", "goods"]):
                desc_col = c_idx
            elif any(k in h_text for k in ["qty", "quantity", "nos", "qnt"]):
                qty_col = c_idx
            elif re.search(r"\b(?:unit\s*price|rate|price|unit\s*rate|mrp|dar)\b", h_text):
                rate_col = c_idx
            elif any(k in h_text for k in ["amount", "total", "net"]):
                total_col = c_idx

        # Defaults if headers were missing or ambiguous
        if desc_col == -1:
            desc_col = 0 if len(header_row) <= 3 else 1
        if total_col == -1:
            total_col = len(header_row) - 1

        items: list[dict[str, Any]] = []
        for row in data_rows:
            if not any(row):
                continue

            desc = row[desc_col] if desc_col < len(row) else ""
            if any(k in desc.lower() for k in ["subtotal", "sub total", "grand total", "terms"]):
                continue

            qty = parse_numeric(row[qty_col]) if qty_col != -1 and qty_col < len(row) else 1.0
            rate = parse_numeric(row[rate_col]) if rate_col != -1 and rate_col < len(row) else 0.0
            total = parse_numeric(row[total_col]) if total_col < len(row) else 0.0

            if total == 0.0 and rate > 0:
                total = round(qty * rate, 2)
            if qty <= 0 and rate > 0 and total > 0:
                qty = round(total / rate, 2)

            if desc or total > 0:
                items.append({
                    "description": desc,
                    "quantity": qty if qty > 0 else 1.0,
                    "unit_price": rate if rate > 0 else total,
                    "line_total": total,
                })

        return items
