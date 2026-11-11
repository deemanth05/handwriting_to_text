"""Unit tests for Surya Multilingual OCR Local Extractor."""

import pytest
from backend.app.schemas.document import DocumentType
from backend.app.services.models.surya_local import SuryaLocalExtractor, parse_numeric


def test_parse_numeric():
    assert parse_numeric("23:60") == 23.60
    assert parse_numeric("Rs. 1,200.50") == 1200.50
    assert parse_numeric("₹450") == 450.0
    assert parse_numeric("$99.95") == 99.95
    assert parse_numeric("invalid") == 0.0


def test_surya_cluster_rows():
    extractor = SuryaLocalExtractor()
    lines = [
        {"text": "Invoice #", "bbox": [50, 100, 150, 120], "confidence": 0.95},
        {"text": "INV-101", "bbox": [160, 100, 250, 120], "confidence": 0.92},
        {"text": "Date:", "bbox": [50, 150, 100, 170], "confidence": 0.90},
        {"text": "12/03/2026", "bbox": [110, 150, 220, 170], "confidence": 0.88},
    ]
    rows = extractor._cluster_rows(lines, y_threshold=20.0)
    assert len(rows) == 2
    assert [b["text"] for b in rows[0]] == ["Invoice #", "INV-101"]
    assert [b["text"] for b in rows[1]] == ["Date:", "12/03/2026"]


def test_surya_parse_invoice():
    extractor = SuryaLocalExtractor()
    # Row with Item description, Qty, Rate, Total
    rows = [
        [
            {"text": "Shree Ganesh Stores", "x_min": 50, "x_max": 250, "y": 50, "score": 0.95},
        ],
        [
            {"text": "Date: 15/01/2026", "x_min": 50, "x_max": 180, "y": 80, "score": 0.90},
            {"text": "Invoice # 9021", "x_min": 200, "x_max": 350, "y": 80, "score": 0.90},
        ],
        [
            {"text": "1L Sunflower Oil", "x_min": 50, "x_max": 200, "y": 140, "score": 0.95},
            {"text": "2", "x_min": 230, "x_max": 250, "y": 140, "score": 0.95},
            {"text": "150.00", "x_min": 300, "x_max": 360, "y": 140, "score": 0.95},
            {"text": "300.00", "x_min": 400, "x_max": 470, "y": 140, "score": 0.95},
        ],
    ]
    raw_lines = ["Shree Ganesh Stores", "Date: 15/01/2026 Invoice # 9021"]
    parsed = extractor._parse_invoice(rows, raw_lines)

    assert parsed["vendor_name"] == "Shree Ganesh Stores"
    assert parsed["invoice_number"] == "9021"
    assert parsed["invoice_date"] == "15/01/2026"
    assert len(parsed["line_items"]) == 1
    item = parsed["line_items"][0]
    assert item["description"] == "1L Sunflower Oil"
    assert item["quantity"] == 2.0
    assert item["unit_price"] == 150.0
    assert item["line_total"] == 300.0


def test_surya_parse_cash_book():
    extractor = SuryaLocalExtractor()
    rows = [
        [
            {"text": "Petty Cash Book", "x_min": 200, "x_max": 400, "y": 30, "score": 0.95},
            {"text": "Month: FEB 2026", "x_min": 450, "x_max": 600, "y": 30, "score": 0.90},
        ],
        [
            {"text": "Date", "x_min": 20, "x_max": 60, "y": 60, "score": 0.9},
            {"text": "Particulars", "x_min": 100, "x_max": 250, "y": 60, "score": 0.9},
            {"text": "Paid (Out)", "x_min": 350, "x_max": 420, "y": 60, "score": 0.9},
            {"text": "Received (In)", "x_min": 450, "x_max": 530, "y": 60, "score": 0.9},
            {"text": "Balance", "x_min": 560, "x_max": 630, "y": 60, "score": 0.9},
        ],
        [
            {"text": "01/02", "x_min": 20, "x_max": 60, "y": 100, "score": 0.9},
            {"text": "Opening Balance", "x_min": 100, "x_max": 240, "y": 100, "score": 0.9},
            {"text": "200.00", "x_min": 450, "x_max": 510, "y": 100, "score": 0.9},
            {"text": "200.00", "x_min": 560, "x_max": 620, "y": 100, "score": 0.9},
        ],
        [
            {"text": "05/02", "x_min": 20, "x_max": 60, "y": 130, "score": 0.9},
            {"text": "Office Stationery", "x_min": 100, "x_max": 240, "y": 130, "score": 0.9},
            {"text": "25.00", "x_min": 350, "x_max": 410, "y": 130, "score": 0.9},
            {"text": "175.00", "x_min": 560, "x_max": 620, "y": 130, "score": 0.9},
        ],
    ]
    raw_lines = ["Petty Cash Book Month: FEB 2026"]
    parsed = extractor._parse_cash_book(rows, raw_lines)

    assert parsed["book_title"] == "Petty Cash Book"
    assert parsed["period"] == "Month: FEB 2026"
    assert len(parsed["ledger_items"]) == 2
    assert parsed["ledger_items"][0]["particulars"] == "Opening Balance"
    assert parsed["ledger_items"][0]["cash_in_credit"] == 200.0
    assert parsed["ledger_items"][0]["running_balance"] == 200.0

    assert parsed["ledger_items"][1]["particulars"] == "Office Stationery"
    assert parsed["ledger_items"][1]["cash_out_debit"] == 25.0
    assert parsed["ledger_items"][1]["running_balance"] == 175.0


@pytest.mark.asyncio
async def test_surya_empty_buffer():
    extractor = SuryaLocalExtractor()
    res = await extractor.extract(b"", DocumentType.INVOICE)
    assert res.status == "ERROR"
    assert "Empty image buffer" in res.error
