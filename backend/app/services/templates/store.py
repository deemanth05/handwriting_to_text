"""Persistent Vendor Template Memory Store.

Stores and queries spatial bounding boxes and column intervals for repeat suppliers
and ledger books in SQLite via SQLAlchemy.
Provides active learning updates when human operators verify documents.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
from typing import Any

import cv2
import numpy as np
from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import ConsensusRecord, DocumentRecord, VendorTemplateRecord
from backend.app.schemas.document import DocumentType
from backend.app.services.layout.bilateral_splitter import BilateralBlockSplitter
from backend.app.services.layout.gutter_detector import AdaptiveColumnDetector
from backend.app.services.layout.zoner import DocumentMacroZoner
from backend.app.services.templates.fingerprint import (
    compute_phash,
    hamming_distance,
    is_generic_header,
    phash_similarity,
)

logger = logging.getLogger(__name__)


def slugify_vendor_name(name: str) -> str:
    """Generate a clean slug identifier from a vendor name."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.lower()).strip("_")
    return cleaned[:64] or "unknown_vendor"


class VendorTemplateStore:
    """Repository for querying, saving, and updating vendor spatial templates."""

    def __init__(self):
        self.zoner = DocumentMacroZoner()
        self.column_detector = AdaptiveColumnDetector()
        self.splitter = BilateralBlockSplitter()

    async def find_match(
        self,
        session: AsyncSession,
        phash: str,
        gstin: str | None = None,
        vendor_name: str | None = None,
        doc_type: str = "INVOICE",
    ) -> tuple[VendorTemplateRecord | None, float]:
        """Find the best matching template for an incoming document.

        Matching Criteria:
        1. Exact GSTIN Match: If GSTIN is present and matches a template's GSTIN.
        2. Dual-Key Match: If GSTIN is absent or no GSTIN match, checks all templates
           for the doc_type:
           - Hamming distance <= 8 bits (>= 87.5% visual similarity)
           - Vendor name fuzzy match >= 85%
           Or Hamming distance <= 4 bits (>= 93.75% visual similarity).

        Returns:
            (matched_record, match_score) where match_score is 0.0 to 1.0.
        """
        # 1. Exact GSTIN match check
        if gstin:
            norm_gstin = gstin.strip().upper()
            stmt = select(VendorTemplateRecord).where(
                VendorTemplateRecord.gstin == norm_gstin,
                VendorTemplateRecord.document_type == doc_type,
            )
            res = await session.execute(stmt)
            exact_match = res.scalars().first()
            if exact_match:
                # Calculate visual similarity for reference
                h_dist = hamming_distance(phash, exact_match.phash)
                sim = 1.0 - (h_dist / 64.0)
                logger.info(
                    "Vendor template matched via exact GSTIN '%s' (Visual sim: %.1f%%)",
                    norm_gstin,
                    sim * 100,
                )
                return exact_match, 1.0

        # 2. Dual-Key Visual + Name search
        stmt = select(VendorTemplateRecord).where(
            VendorTemplateRecord.document_type == doc_type
        )
        res = await session.execute(stmt)
        all_templates = res.scalars().all()

        best_cand: VendorTemplateRecord | None = None
        best_score = 0.0

        for cand in all_templates:
            h_dist = hamming_distance(phash, cand.phash)
            sim = phash_similarity(phash, cand.phash)  # 1.0 - dist/64

            # Case A: Both vendor names available
            if vendor_name and cand.vendor_name:
                name_sim = (
                    fuzz.token_sort_ratio(vendor_name.lower(), cand.vendor_name.lower()) / 100.0
                )
                if h_dist <= 8 and name_sim >= 0.85:
                    score = 0.5 * sim + 0.5 * name_sim
                    if score > best_score:
                        best_score = score
                        best_cand = cand
                elif h_dist <= 4 and name_sim >= 0.60:
                    score = 0.5 * sim + 0.5 * name_sim
                    # h_dist <= 4 indicates nearly identical visual structure; qualify score to >= 0.85
                    score = max(0.85, score)
                    if score > best_score:
                        best_score = score
                        best_cand = cand
            else:
                # Case B: Rely on visual pHash (tight threshold <= 4 bits)
                if h_dist <= 4:
                    score = sim
                    if score > best_score:
                        best_score = score
                        best_cand = cand

        if best_cand and best_score >= 0.85:
            logger.info(
                "Vendor template matched via Dual-Key: '%s' (Score: %.2f)",
                best_cand.vendor_name,
                best_score,
            )
            return best_cand, best_score

        return None, 0.0

    async def save_or_update(
        self,
        session: AsyncSession,
        vendor_name: str,
        gstin: str | None,
        phash: str,
        doc_type: str,
        table_zone: dict[str, Any],
        header_zone: dict[str, Any] | None = None,
        summary_zone: dict[str, Any] | None = None,
    ) -> VendorTemplateRecord:
        """Create a new vendor template or update an existing one."""
        v_name = vendor_name.strip() if vendor_name else "Unknown Vendor"
        v_slug = slugify_vendor_name(v_name)
        v_key = f"{v_slug}_{doc_type.lower()}"
        norm_gstin = gstin.strip().upper() if gstin else None

        # Check if matching template already exists
        existing_match, score = await self.find_match(
            session=session,
            phash=phash,
            gstin=norm_gstin,
            vendor_name=v_name,
            doc_type=doc_type,
        )

        now = datetime.now(UTC)

        if existing_match:
            existing_match.sample_count += 1
            existing_match.updated_at = now
            existing_match.phash = phash
            # Only update table_zone if valid columns were harvested
            if table_zone and table_zone.get("columns"):
                existing_match.table_zone_json = json.dumps(table_zone)
            if header_zone:
                existing_match.header_zone_json = json.dumps(header_zone)
            if summary_zone:
                existing_match.summary_zone_json = json.dumps(summary_zone)
            if norm_gstin and not existing_match.gstin:
                existing_match.gstin = norm_gstin
            # If a clean vendor name is provided, update it without character length bias
            if v_name and v_name != "Unknown Vendor" and not is_generic_header(v_name):
                existing_match.vendor_name = v_name
                existing_match.vendor_key = v_key

            await session.commit()
            await session.refresh(existing_match)
            logger.info(
                "Updated existing vendor template for '%s' (sample_count=%d)",
                existing_match.vendor_name,
                existing_match.sample_count,
            )
            return existing_match

        # Otherwise create new record
        new_record = VendorTemplateRecord(
            vendor_key=v_key,
            vendor_name=v_name,
            gstin=norm_gstin,
            phash=phash,
            document_type=doc_type,
            table_zone_json=json.dumps(table_zone),
            header_zone_json=json.dumps(header_zone) if header_zone else None,
            summary_zone_json=json.dumps(summary_zone) if summary_zone else None,
            sample_count=1,
            created_at=now,
            updated_at=now,
        )
        session.add(new_record)
        await session.commit()
        await session.refresh(new_record)
        logger.info("Created new vendor template for '%s' (id=%s)", v_name, new_record.id)
        return new_record

    def harvest_layout_from_image(
        self,
        img: np.ndarray,
        ocr_boxes: list[Any],
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
        """Derive normalized table_zone, header_zone, and summary_zone from image and OCR boxes."""
        h, w = img.shape[:2]
        standard_boxes = self.zoner.standardize_boxes(ocr_boxes)
        zones = self.zoner.zone(standard_boxes, doc_type=doc_type, doc_width=w, doc_height=h)

        # Detect columns
        columns = self.column_detector.detect_columns(
            table_rows=zones.table_rows,
            table_header_row=zones.table_header_row,
            doc_width=w,
            doc_type=doc_type,
        )

        # Compute table vertical boundaries
        y_min_px = float(zones.table_rows[0][0]["y_min"]) if zones.table_rows and zones.table_rows[0] else 0.20 * h
        # Start table with a small safety margin above first row
        y_min_px = max(0.0, y_min_px - 0.02 * h)

        # Summary zone start: where below_table_rows or summary_boxes begin
        if zones.summary_boxes:
            y_max_px = float(min(b["y_min"] for b in zones.summary_boxes))
        elif zones.table_rows and zones.table_rows[-1]:
            y_max_px = float(zones.table_rows[-1][0]["y_max"]) + 0.05 * h
        else:
            y_max_px = 0.85 * h

        table_zone = {
            "y_min_ratio": round(y_min_px / h, 4),
            "y_max_ratio": round(min(1.0, y_max_px / h), 4),
            "columns": [
                {
                    "col_id": col.col_id,
                    "col_type": col.col_type.value,
                    "x_start_ratio": round(col.x_start / w, 4),
                    "x_end_ratio": round(col.x_end / w, 4),
                    "header_text": col.header_text,
                }
                for col in columns
            ],
        }

        header_zone = {
            "y_min_ratio": 0.0,
            "y_max_ratio": round(y_min_px / h, 4),
        }

        summary_zone = {
            "y_min_ratio": round(min(1.0, y_max_px / h), 4),
            "y_max_ratio": 1.0,
        }

        return table_zone, header_zone, summary_zone

    async def learn_from_verification(
        self,
        session: AsyncSession,
        document_id: str,
        verified_fields: dict[str, Any],
        verified_line_items: list[dict[str, Any]],
        verified_ledger_items: list[dict[str, Any]],
    ) -> VendorTemplateRecord | None:
        """Active Learning: update vendor template memory cache when an operator confirms ground truth."""
        try:
            # 1. Fetch DocumentRecord
            doc_res = await session.execute(
                select(DocumentRecord).where(DocumentRecord.id == document_id)
            )
            doc = doc_res.scalars().first()
            if not doc:
                logger.warning("learn_from_verification: Document %s not found.", document_id)
                return None

            # 2. Locate stored image
            img_path = settings.UPLOAD_DIR / f"{document_id}_page_1.jpg"
            if not img_path.exists():
                img_path = settings.UPLOAD_DIR / f"{document_id}_{doc.filename}"

            if not img_path.exists():
                logger.warning("learn_from_verification: Image for %s missing on disk.", document_id)
                return None

            img = cv2.imread(str(img_path))
            if img is None:
                logger.warning("learn_from_verification: Failed to decode image %s", img_path)
                return None

            # 3. Compute pHash
            phash = compute_phash(img)

            # 4. Resolve vendor name and GSTIN
            vendor_name = verified_fields.get("vendor_name")
            gstin = verified_fields.get("gstin")

            # Fallback to Consensus Record if missing from verification payload
            if not vendor_name or not gstin:
                cons_res = await session.execute(
                    select(ConsensusRecord).where(ConsensusRecord.document_id == document_id)
                )
                cons = cons_res.scalars().first()
                if cons:
                    try:
                        c_data = json.loads(cons.reconciled_json)
                        c_fields = c_data.get("fields", {})
                        if not vendor_name and "vendor_name" in c_fields:
                            vendor_name = c_fields["vendor_name"].get("value")
                        if not gstin and "gstin" in c_fields:
                            gstin = c_fields["gstin"].get("value")
                    except Exception:
                        pass

            if not vendor_name:
                vendor_name = "Verified Vendor"

            # 5. Run local OCR to harvest layout anchors
            from rapidocr_onnxruntime import RapidOCR
            ocr_engine = RapidOCR()
            ocr_results, _ = ocr_engine(img)

            doc_type_enum = DocumentType.INVOICE
            try:
                doc_type_enum = DocumentType(doc.document_type)
            except ValueError:
                pass

            table_zone, header_zone, summary_zone = self.harvest_layout_from_image(
                img=img,
                ocr_boxes=ocr_results or [],
                doc_type=doc_type_enum,
            )

            # 6. Save or update template record
            template = await self.save_or_update(
                session=session,
                vendor_name=vendor_name,
                gstin=gstin,
                phash=phash,
                doc_type=doc.document_type,
                table_zone=table_zone,
                header_zone=header_zone,
                summary_zone=summary_zone,
            )
            logger.info(
                "Active Learning: Successfully updated template '%s' from human verification on %s",
                template.vendor_name,
                document_id,
            )
            return template
        except Exception as e:
            logger.error("learn_from_verification failed for document %s: %s", document_id, e)
            return None

    async def list_templates(
        self,
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VendorTemplateRecord]:
        """List cached vendor templates."""
        stmt = (
            select(VendorTemplateRecord)
            .order_by(VendorTemplateRecord.sample_count.desc(), VendorTemplateRecord.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def get_template(
        self,
        session: AsyncSession,
        template_id: str,
    ) -> VendorTemplateRecord | None:
        """Fetch template by ID."""
        stmt = select(VendorTemplateRecord).where(VendorTemplateRecord.id == template_id)
        res = await session.execute(stmt)
        return res.scalars().first()

    async def delete_template(
        self,
        session: AsyncSession,
        template_id: str,
    ) -> bool:
        """Delete template by ID."""
        stmt = delete(VendorTemplateRecord).where(VendorTemplateRecord.id == template_id)
        res = await session.execute(stmt)
        await session.commit()
        return res.rowcount > 0


# Global singleton instance
vendor_template_store = VendorTemplateStore()
