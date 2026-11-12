"""Tests for Vendor Template API Routes & End-to-End Extraction Flow."""

import json
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ConsensusRecord, DocumentRecord, VendorTemplateRecord
from backend.app.schemas.document import DocumentType
from backend.app.services.ensemble import ensemble_dispatcher
from backend.app.services.models.mock_extractor import MockVisionExtractor
from backend.app.services.templates import (
    compute_phash,
    template_fast_extractor,
    vendor_template_store,
)

SAMPLE_DIR = Path("sample_dataset")


@pytest.mark.asyncio
async def test_template_api_crud(client: AsyncClient, db_session: AsyncSession):
    """Test /api/v1/templates listing, retrieval, and deletion endpoints."""
    sample_table = {
        "y_min_ratio": 0.20,
        "y_max_ratio": 0.80,
        "columns": [
            {"col_id": 0, "col_type": "INDEX", "x_start_ratio": 0.05, "x_end_ratio": 0.15},
            {"col_id": 1, "col_type": "DESCRIPTION", "x_start_ratio": 0.16, "x_end_ratio": 0.55},
        ],
    }

    rec = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Mahalaxmi Steel Traders",
        gstin="27AABCM9999M1Z9",
        phash="8f4b1e1ee92d9292",
        doc_type="INVOICE",
        table_zone=sample_table,
    )

    # 1. List templates
    resp_list = await client.get("/api/v1/templates")
    assert resp_list.status_code == 200
    templates = resp_list.json()
    assert len(templates) >= 1
    found = next((t for t in templates if t["id"] == rec.id), None)
    assert found is not None
    assert found["vendor_name"] == "Mahalaxmi Steel Traders"
    assert found["gstin"] == "27AABCM9999M1Z9"

    # 2. Get single template detail
    resp_get = await client.get(f"/api/v1/templates/{rec.id}")
    assert resp_get.status_code == 200
    detail = resp_get.json()
    assert detail["id"] == rec.id
    assert "columns" in detail["table_zone"]
    assert len(detail["table_zone"]["columns"]) == 2

    # 3. Delete template
    resp_del = await client.delete(f"/api/v1/templates/{rec.id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["id"] == rec.id

    # 4. Confirm 404 after deletion
    resp_after = await client.get(f"/api/v1/templates/{rec.id}")
    assert resp_after.status_code == 404


@pytest.mark.asyncio
async def test_active_learning_from_human_verification(
    client: AsyncClient, db_session: AsyncSession
):
    """POST /documents/{id}/verify must trigger active learning and create/update template."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img_bytes = img_path.read_bytes()

    # Pre-populate DocumentRecord in database
    doc_id = "test-doc-active-learning"
    doc_rec = DocumentRecord(
        id=doc_id,
        filename="sample_invoice.png",
        content_type="image/png",
        document_type="INVOICE",
        overall_confidence=0.85,
        math_valid=True,
        page_count=1,
        status="NEEDS_REVIEW",
    )
    db_session.add(doc_rec)
    await db_session.commit()

    # Ensure file is saved in UPLOAD_DIR for the test
    from backend.app.config import settings
    upload_file = settings.UPLOAD_DIR / f"{doc_id}_page_1.jpg"
    upload_file.write_bytes(img_bytes)

    try:
        verify_payload = {
            "verified_fields": {
                "vendor_name": "Shree Ganesh Verified Stores",
                "gstin": "27AABCS1429B1Z1",
                "invoice_date": "2026-10-31",
                "subtotal": 1350.0,
                "tax_amount": 67.5,
                "discount_amount": 17.5,
                "grand_total": 1400.0,
            },
            "verified_line_items": [
                {
                    "description": "Atta 5kg",
                    "quantity": 2.0,
                    "unit_price": 240.0,
                    "line_total": 480.0,
                }
            ],
            "verified_ledger_items": [],
            "verified_by": "qa-operator-1",
        }

        resp = await client.post(f"/api/v1/documents/{doc_id}/verify", json=verify_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "VERIFIED"
        assert data["template_updated"] is True
        assert data["template_id"] is not None

        # Verify template exists in DB
        tmpl = await vendor_template_store.get_template(
            session=db_session, template_id=data["template_id"]
        )
        assert tmpl is not None
        assert tmpl.vendor_name == "Shree Ganesh Verified Stores"
        assert tmpl.gstin == "27AABCS1429B1Z1"
    finally:
        if upload_file.exists():
            upload_file.unlink()


@pytest.mark.asyncio
async def test_end_to_end_fast_path_extraction(
    client: AsyncClient, db_session: AsyncSession
):
    """Uploading an invoice with a matching cached template executes the sub-second Fast Path."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img_bytes = img_path.read_bytes()
    img = cv2_imread = cv2 = __import__("cv2")
    img = cv2.imread(str(img_path))
    assert img is not None

    # Harvest actual layout to seed the template cache
    ocr_results, _ = template_fast_extractor.ocr_engine(img)
    tbl_zone, hdr_zone, smr_zone = vendor_template_store.harvest_layout_from_image(
        img=img,
        ocr_boxes=ocr_results,
        doc_type=DocumentType.INVOICE,
    )

    phash = compute_phash(img_bytes)

    # Seed template cache
    seed_record = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="SHREE GANESH GENERAL STORES",
        gstin="27AABCS1429B1Z1",
        phash=phash,
        doc_type="INVOICE",
        table_zone=tbl_zone,
        header_zone=hdr_zone,
        summary_zone=smr_zone,
    )
    assert seed_record.id is not None

    # Upload document to /api/v1/extract
    files = {"file": ("shree_ganesh_invoice.png", img_bytes, "image/png")}
    data = {"doc_type": "INVOICE"}
    resp = await client.post("/api/v1/extract", files=files, data=data)

    assert resp.status_code == 200
    res_data = resp.json()

    # Must have matched fast path!
    assert res_data["template_matched"] is True
    assert res_data["template_vendor"] == "SHREE GANESH GENERAL STORES"
    assert "template_cache" in res_data["models_participated"]
    assert res_data["math_validation"]["is_valid"] is True
    assert len(res_data["line_items"]) >= 2
    assert res_data["processing_time_ms"] < 3000.0
