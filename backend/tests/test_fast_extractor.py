"""Tests for Sub-Second TemplateFastExtractor (Zero Mock Data, Real Image Pixels)."""

import json
from pathlib import Path
import time
import cv2
import pytest

from backend.app.db.models import VendorTemplateRecord
from backend.app.schemas.document import DocumentType
from backend.app.services.templates import (
    compute_phash,
    template_fast_extractor,
    vendor_template_store,
)

SAMPLE_DIR = Path("sample_dataset")


def test_fast_extractor_real_sample_invoice():
    """Verify fast-path extraction directly parses line items and math from real invoice image."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img_bytes = img_path.read_bytes()
    img = cv2.imread(str(img_path))
    assert img is not None

    h, w = img.shape[:2]
    phash = compute_phash(img_bytes)

    # Harvest actual layout from image to create golden template
    ocr_results, _ = template_fast_extractor.ocr_engine(img)
    tbl_zone, hdr_zone, smr_zone = vendor_template_store.harvest_layout_from_image(
        img=img,
        ocr_boxes=ocr_results,
        doc_type=DocumentType.INVOICE,
    )

    template = VendorTemplateRecord(
        id="tmpl-test-invoice-1",
        vendor_key="shree_ganesh_general_stores_invoice",
        vendor_name="SHREE GANESH GENERAL STORES",
        gstin="27AABCS1429B1Z1",
        phash=phash,
        document_type="INVOICE",
        table_zone_json=json.dumps(tbl_zone),
        header_zone_json=json.dumps(hdr_zone) if hdr_zone else None,
        summary_zone_json=json.dumps(smr_zone) if smr_zone else None,
        sample_count=1,
    )

    t0 = time.perf_counter()
    resp = template_fast_extractor.extract(
        image_bytes=img_bytes,
        template=template,
        document_id="doc-fast-test-1",
        doc_type=DocumentType.INVOICE,
    )
    duration_ms = (time.perf_counter() - t0) * 1000

    assert resp is not None, "Fast path extraction returned None on valid invoice template."
    assert resp.template_matched is True
    assert resp.template_vendor == "SHREE GANESH GENERAL STORES"
    assert resp.math_validation.is_valid is True
    assert len(resp.line_items) >= 2

    # Verify arithmetic validation: each row satisfies Qty * Unit Price == Line Total
    for item in resp.line_items:
        q = item.quantity.value or 0.0
        p = item.unit_price.value or 0.0
        tot = item.line_total.value or 0.0
        assert item.row_math_valid is True
        assert abs(round(q * p, 2) - round(tot, 2)) <= 0.05 * tot or abs(round(q * p, 2) - round(tot, 2)) <= 1.0

    # Latency should be fast local execution (< 3000ms on CPU vs 20,000ms on VLM cold path)
    assert resp.processing_time_ms < 3000.0, f"Fast path latency exceeded 3000ms: {resp.processing_time_ms}ms"


def test_fast_extractor_fallback_on_invalid_layout():
    """When template column coordinates are corrupted, fast extractor must return None."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img_bytes = img_path.read_bytes()

    # Corrupt columns by putting non-existent horizontal ranges
    corrupt_table = {
        "y_min_ratio": 0.30,
        "y_max_ratio": 0.60,
        "columns": [
            # Inverted / invalid intervals
            {"col_id": 0, "col_type": "RATE", "x_start_ratio": 0.01, "x_end_ratio": 0.02},
            {"col_id": 1, "col_type": "QUANTITY", "x_start_ratio": 0.03, "x_end_ratio": 0.04},
        ],
    }

    template = VendorTemplateRecord(
        id="tmpl-corrupt",
        vendor_key="corrupt_vendor",
        vendor_name="Corrupt Vendor",
        gstin=None,
        phash="8f4b1e1ee92d9292",
        document_type="INVOICE",
        table_zone_json=json.dumps(corrupt_table),
    )

    # Should return None, triggering automatic fallback to cold path
    resp = template_fast_extractor.extract(
        image_bytes=img_bytes,
        template=template,
        document_id="doc-corrupt",
        doc_type=DocumentType.INVOICE,
    )
    assert resp is None


def test_fast_extractor_real_sample_khata():
    """Verify template harvesting and fast-path extraction on sample_khata.png."""
    img_path = SAMPLE_DIR / "sample_khata.png"
    img_bytes = img_path.read_bytes()
    img = cv2.imread(str(img_path))
    assert img is not None

    ocr_results, _ = template_fast_extractor.ocr_engine(img)
    tbl_zone, hdr_zone, smr_zone = vendor_template_store.harvest_layout_from_image(
        img=img,
        ocr_boxes=ocr_results,
        doc_type=DocumentType.KHATA_LEDGER,
    )

    assert tbl_zone["columns"], "Khata template failed to detect column channels."
    phash = compute_phash(img_bytes)

    template = VendorTemplateRecord(
        id="tmpl-test-khata-1",
        vendor_key="rameshwar_kirana_khata",
        vendor_name="Rameshwar Kirana Khata Bahi",
        gstin=None,
        phash=phash,
        document_type="KHATA_LEDGER",
        table_zone_json=json.dumps(tbl_zone),
        header_zone_json=json.dumps(hdr_zone) if hdr_zone else None,
        summary_zone_json=json.dumps(smr_zone) if smr_zone else None,
        sample_count=1,
    )

    resp = template_fast_extractor.extract(
        image_bytes=img_bytes,
        template=template,
        document_id="doc-fast-khata-1",
        doc_type=DocumentType.KHATA_LEDGER,
        precomputed_ocr_results=ocr_results,
    )

    assert resp is not None, "Fast path extraction failed on sample_khata.png"
    assert resp.template_matched is True
    assert resp.math_validation.is_valid is True
    assert len(resp.line_items) == 3

    # Check that items satisfy row math
    for it in resp.line_items:
        assert it.row_math_valid is True

    # Check Khata-specific summary fields
    assert "jama_credit" in resp.fields
    assert resp.fields["jama_credit"].value == 500.0
    assert "closing_balance" in resp.fields
    assert resp.fields["closing_balance"].value == 500.0


def test_fast_extractor_slash_invoice_no_and_dotted_date():
    """Verify invoice numbers with slashes and dotted dates are extracted without truncation."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img_bytes = img_path.read_bytes()
    img = cv2.imread(str(img_path))

    ocr_results, _ = template_fast_extractor.ocr_engine(img)
    tbl_zone, hdr_zone, smr_zone = vendor_template_store.harvest_layout_from_image(
        img=img,
        ocr_boxes=ocr_results,
        doc_type=DocumentType.INVOICE,
    )

    # Inject invoice number with forward slashes and dotted date into OCR boxes
    custom_ocr = [
        item for item in ocr_results
        if "INV-" not in str(item[1]) and "2026-10-31" not in str(item[1])
    ]
    custom_ocr.append([[[100, 50], [300, 50], [300, 80], [100, 80]], "Invoice No: INV/2026-27/0042", 0.99])
    custom_ocr.append([[[400, 50], [550, 50], [550, 80], [400, 80]], "Date: 25.10.2026", 0.99])

    template = VendorTemplateRecord(
        id="tmpl-slash-test",
        vendor_key="slash_vendor_invoice",
        vendor_name="SHREE GANESH GENERAL STORES",
        gstin="27AABCS1429B1Z1",
        phash=compute_phash(img_bytes),
        document_type="INVOICE",
        table_zone_json=json.dumps(tbl_zone),
        header_zone_json=json.dumps(hdr_zone) if hdr_zone else None,
        summary_zone_json=json.dumps(smr_zone) if smr_zone else None,
        sample_count=1,
    )

    resp = template_fast_extractor.extract(
        image_bytes=img_bytes,
        template=template,
        document_id="doc-slash-test",
        doc_type=DocumentType.INVOICE,
        precomputed_ocr_results=custom_ocr,
    )

    assert resp is not None
    assert resp.fields["invoice_number"].value == "INV/2026-27/0042"
    assert resp.fields["invoice_date"].value == "25.10.2026"


def test_fast_extractor_dynamic_row_expansion():
    """Verify that an invoice with items extending beyond the template's harvested y_max_ratio

    dynamically expands to capture all items rather than rigidly clipping them.
    """
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img_bytes = img_path.read_bytes()
    img = cv2.imread(str(img_path))

    ocr_results, _ = template_fast_extractor.ocr_engine(img)
    tbl_zone, hdr_zone, smr_zone = vendor_template_store.harvest_layout_from_image(
        img=img,
        ocr_boxes=ocr_results,
        doc_type=DocumentType.INVOICE,
    )

    # Artificially restrict y_max_ratio to 0.25 (below only the first 2 items)
    tbl_small = dict(tbl_zone)
    tbl_small["y_max_ratio"] = 0.25

    template = VendorTemplateRecord(
        id="tmpl-dynamic-row-test",
        vendor_key="dynamic_vendor_invoice",
        vendor_name="SHREE GANESH GENERAL STORES",
        gstin="27AABCS1429B1Z1",
        phash=compute_phash(img_bytes),
        document_type="INVOICE",
        table_zone_json=json.dumps(tbl_small),
        header_zone_json=json.dumps(hdr_zone) if hdr_zone else None,
        summary_zone_json=json.dumps(smr_zone) if smr_zone else None,
        sample_count=1,
    )

    resp = template_fast_extractor.extract(
        image_bytes=img_bytes,
        template=template,
        document_id="doc-dynamic-row-test",
        doc_type=DocumentType.INVOICE,
        precomputed_ocr_results=ocr_results,
    )

    assert resp is not None
    assert resp.math_validation.is_valid is True
    assert len(resp.line_items) == 4
    for it in resp.line_items:
        assert it.row_math_valid is True
