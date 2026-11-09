"""Tests for RapidOCR local ONNX extractor and schema parsing."""

import pytest

from backend.app.schemas.document import DocumentType
from backend.app.services.models.rapidocr_local import RapidOCRLocalExtractor


@pytest.mark.asyncio
async def test_rapidocr_local_invoice(sample_invoice_bytes: bytes):
    extractor = RapidOCRLocalExtractor()
    res = await extractor.extract(sample_invoice_bytes, DocumentType.INVOICE)

    assert res.status == "SUCCESS"
    assert res.parsed_json is not None
    # Vendor name extracted
    assert "SHREEGANESH" in res.parsed_json.get("vendor_name", "").upper()
    # Line items extracted
    items = res.parsed_json.get("line_items", [])
    assert len(items) >= 3
    # Check item details
    descriptions = [it["description"].lower() for it in items]
    assert any("atta" in d for d in descriptions)
    assert any("toor dal" in d for d in descriptions)


@pytest.mark.asyncio
async def test_rapidocr_local_empty_buffer():
    extractor = RapidOCRLocalExtractor()
    res = await extractor.extract(b"", DocumentType.INVOICE)
    assert res.status == "ERROR"
    assert "failed" in res.error.lower()


@pytest.mark.asyncio
async def test_rapidocr_local_cash_book(sample_cash_book_bytes: bytes):
    extractor = RapidOCRLocalExtractor()
    res = await extractor.extract(sample_cash_book_bytes, DocumentType.CASH_BOOK)

    assert res.status == "SUCCESS"
    assert res.parsed_json is not None
    assert "Petty Cash" in res.parsed_json.get("book_title", "")
    items = res.parsed_json.get("ledger_items", [])
    assert len(items) >= 10
    # Check that first row is Opening Balance
    assert "opening" in items[0]["particulars"].lower()
    # Check that amounts are non-zero
    assert items[0]["running_balance"] > 0 or items[0]["cash_in_credit"] > 0


def test_rapidocr_flexible_header_columns():
    extractor = RapidOCRLocalExtractor()
    # Simulate a 600px width document with Debit/Credit/Balance header (no 'details' keyword)
    rows = [
        [
            {"text": "Date", "x_min": 20, "x_max": 60, "y": 50, "score": 0.9},
            {"text": "Particulars", "x_min": 100, "x_max": 200, "y": 50, "score": 0.9},
            {"text": "Debit", "x_min": 300, "x_max": 350, "y": 50, "score": 0.9},
            {"text": "Credit", "x_min": 400, "x_max": 450, "y": 50, "score": 0.9},
            {"text": "Balance", "x_min": 500, "x_max": 570, "y": 50, "score": 0.9},
        ],
        [
            {"text": "01/02", "x_min": 20, "x_max": 60, "y": 100, "score": 0.9},
            {"text": "Opening Balance", "x_min": 100, "x_max": 220, "y": 100, "score": 0.9},
            {"text": "0.00", "x_min": 300, "x_max": 340, "y": 100, "score": 0.9},
            {"text": "200.00", "x_min": 400, "x_max": 460, "y": 100, "score": 0.9},
            {"text": "200.00", "x_min": 500, "x_max": 560, "y": 100, "score": 0.9},
        ],
    ]
    parsed = extractor._parse_cash_book(rows, ["Header line", "Data line"])
    items = parsed.get("ledger_items", [])
    assert len(items) == 1
    assert items[0]["particulars"] == "Opening Balance"
    assert items[0]["cash_in_credit"] == 200.0
    assert items[0]["running_balance"] == 200.0
