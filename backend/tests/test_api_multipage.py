"""Integration Tests for Multi-Page PDF and ZIP Uploads & Extraction API."""

import io
import zipfile
import pytest
from httpx import AsyncClient
from PIL import Image
import pypdfium2 as pdfium
from sqlalchemy.ext.asyncio import AsyncSession


def _create_synthetic_invoice_page(text: str) -> bytes:
    # 800x400 white image
    img = Image.new("RGB", (800, 400), color=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()


def _create_synthetic_pdf(page_count: int = 2) -> bytes:
    pdf = pdfium.PdfDocument.new()
    for _ in range(page_count):
        pdf.new_page(width=595, height=842)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


@pytest.mark.asyncio
async def test_api_extract_multipage_pdf(client: AsyncClient, db_session: AsyncSession):
    pdf_bytes = _create_synthetic_pdf(page_count=2)

    files = {
        "file": ("supplier_bill_2pages.pdf", pdf_bytes, "application/pdf"),
    }
    data = {
        "doc_type": "INVOICE",
    }

    res = await client.post("/api/v1/extract", files=files, data=data)
    assert res.status_code == 200
    doc = res.json()

    assert doc["document_id"]
    assert doc["page_count"] == 2
    assert len(doc["pages"]) == 2

    doc_id = doc["document_id"]

    # 1. Test image retrieval for Page 1
    res_p1 = await client.get(f"/api/v1/documents/{doc_id}/image?page=1")
    assert res_p1.status_code == 200
    assert "image/jpeg" in res_p1.headers["content-type"]
    assert len(res_p1.content) > 0

    # 2. Test image retrieval for Page 2
    res_p2 = await client.get(f"/api/v1/documents/{doc_id}/image?page=2")
    assert res_p2.status_code == 200
    assert "image/jpeg" in res_p2.headers["content-type"]
    assert len(res_p2.content) > 0

    # 2b. Test out-of-range and invalid page requests (must return 404, not fallback to PDF)
    res_p3 = await client.get(f"/api/v1/documents/{doc_id}/image?page=3")
    assert res_p3.status_code == 404
    assert "out of range" in res_p3.json()["detail"]

    res_p0 = await client.get(f"/api/v1/documents/{doc_id}/image?page=0")
    assert res_p0.status_code == 404
    assert "Invalid page" in res_p0.json()["detail"]

    # 3. Test pages metadata endpoint
    res_pages = await client.get(f"/api/v1/documents/{doc_id}/pages")
    assert res_pages.status_code == 200
    pages_meta = res_pages.json()
    assert pages_meta["document_id"] == doc_id
    assert pages_meta["page_count"] == 2
    assert pages_meta["content_type"] == "application/pdf"

    # 4. Test multi-page Excel export
    res_excel = await client.get(f"/api/v1/documents/{doc_id}/export/excel")
    assert res_excel.status_code == 200

    # 5. Test multi-page Tally export
    res_tally = await client.get(f"/api/v1/documents/{doc_id}/export/tally")
    assert res_tally.status_code == 200


@pytest.mark.asyncio
async def test_api_extract_stapled_zip_bundle(client: AsyncClient, db_session: AsyncSession):
    p1 = _create_synthetic_invoice_page("Page 1")
    p2 = _create_synthetic_invoice_page("Page 2")

    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, mode="w") as zf:
        zf.writestr("page_01.jpg", p1)
        zf.writestr("page_02.jpg", p2)

    files = {
        "file": ("stapled_khata.zip", zip_io.getvalue(), "application/zip"),
    }
    data = {
        "doc_type": "KHATA_LEDGER",
    }

    res = await client.post("/api/v1/extract", files=files, data=data)
    assert res.status_code == 200
    doc = res.json()

    assert doc["document_id"]
    assert doc["page_count"] == 2
    assert doc["document_type"] == "KHATA_LEDGER"
