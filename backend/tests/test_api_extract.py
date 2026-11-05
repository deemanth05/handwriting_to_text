"""Tests for FastAPI HTTP Endpoints."""

import pytest
from httpx import AsyncClient

from backend.app.services.ensemble import ensemble_dispatcher
from backend.app.services.models.mock_extractor import MockVisionExtractor


@pytest.mark.asyncio
async def test_health_endpoints(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"

    router_resp = await client.get("/api/v1/health/freellmapi")
    assert router_resp.status_code == 200


@pytest.mark.asyncio
async def test_extract_invalid_file(client: AsyncClient):
    # Upload text file instead of image
    files = {"file": ("malicious.txt", b"plain text content", "text/plain")}
    resp = await client.post("/api/v1/extract", files=files)
    assert resp.status_code == 400
    assert "Unsupported or unsafe" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_extract_valid_image_end_to_end(client: AsyncClient, sample_invoice_bytes: bytes):
    # Override ensemble dispatcher with mock extractors for deterministic test
    mock_payload = {
        "vendor_name": "SHREE GANESH GENERAL STORES",
        "invoice_date": "2026-10-31",
        "invoice_number": "INV-2026-089",
        "line_items": [
            {"description": "Atta 5kg", "quantity": 2.0, "unit_price": 240.0, "line_total": 480.0},
            {
                "description": "Toor Dal 1kg",
                "quantity": 3.0,
                "unit_price": 160.0,
                "line_total": 480.0,
            },
        ],
        "subtotal": 960.0,
        "tax_amount": 40.0,
        "discount_amount": 0.0,
        "grand_total": 1000.0,
    }

    orig_extractors = ensemble_dispatcher.extractors
    ensemble_dispatcher.extractors = [
        MockVisionExtractor("gemini_vlm", "m1", mock_payload),
        MockVisionExtractor("qwen_vl", "m2", mock_payload),
        MockVisionExtractor("hybrid_ocr", "m3", mock_payload),
    ]

    try:
        files = {"file": ("invoice.png", sample_invoice_bytes, "image/png")}
        data = {"doc_type": "INVOICE"}
        resp = await client.post("/api/v1/extract", files=files, data=data)

        assert resp.status_code == 200
        result = resp.json()

        assert "document_id" in result
        doc_id = result["document_id"]
        assert result["overall_confidence"] >= 0.90
        assert result["math_validation"]["is_valid"] is True
        assert result["fields"]["vendor_name"]["agreement"] == "3/3"
        assert len(result["line_items"]) == 2

        # Test document retrieval endpoint
        get_resp = await client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["document_id"] == doc_id

        # Test document list endpoint
        list_resp = await client.get("/api/v1/documents")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # Test document image streaming endpoint
        img_resp = await client.get(f"/api/v1/documents/{doc_id}/image")
        assert img_resp.status_code == 200
        assert len(img_resp.content) > 0

        # Test human verification endpoint (HITL)
        verify_payload = {
            "verified_fields": {"vendor_name": "SHREE GANESH GENERAL STORES"},
            "verified_line_items": [
                {"description": "Atta 5kg", "quantity": 2.0, "unit_price": 240.0, "line_total": 480.0}
            ],
            "verified_by": "qa-reviewer",
        }
        v_resp = await client.post(f"/api/v1/documents/{doc_id}/verify", json=verify_payload)
        assert v_resp.status_code == 200
        assert v_resp.json()["status"] == "VERIFIED"

    finally:
        ensemble_dispatcher.extractors = orig_extractors
