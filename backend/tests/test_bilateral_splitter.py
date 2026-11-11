"""Unit tests for BilateralBlockSplitter and summary/footer disambiguation."""

import pytest

from backend.app.services.layout.bilateral_splitter import (
    BilateralBlockSplitter,
    parse_numeric,
    words_to_number,
)


def test_parse_numeric_quirks():
    assert parse_numeric("23:60") == 23.60
    assert parse_numeric("Rs. 1,200.50") == 1200.50
    assert parse_numeric("₹450") == 450.0
    assert parse_numeric("$99.95") == 99.95
    assert parse_numeric("082.20") == 82.20
    assert parse_numeric("1.250.00") == 1250.00
    assert parse_numeric("12.50.00") == 1250.00
    assert parse_numeric("-50.00") == -50.00
    assert parse_numeric("invalid") == 0.0
    assert parse_numeric("") == 0.0


def test_words_to_number():
    assert words_to_number("INR Eight Thousand Nine Hundred Ninety Only") == 8990.0
    assert words_to_number("INR Eigh+ Thousand Nine Hundred Ninety Only.") == 8990.0
    assert words_to_number("Rupees One Lakh Twenty Five Thousand Only") == 125000.0
    assert words_to_number("Five Hundred Forty Two") == 542.0
    assert words_to_number("Two Thousand") == 2000.0
    assert words_to_number("Eight Thousand Nine Hundred Ninety Rupees and Fifty Paise Only") == 8990.50
    assert words_to_number("Eight Thousand Nine Hundred Ninety and 40/100 Only") == 8990.40
    assert words_to_number("Twenty-Five Thousand") == 25000.0
    assert words_to_number("Random text without numbers") is None
    assert words_to_number("") is None


def test_bilateral_splitter_clean_split():
    splitter = BilateralBlockSplitter()
    doc_width = 1000.0

    boxes = [
        # Left block (narrative)
        {"text": "Amount Chargeable (in words):", "x_min": 50, "x_max": 300, "y": 700},
        {"text": "INR Eight Thousand Nine Hundred Ninety Only.", "x_min": 50, "x_max": 450, "y": 725},
        {"text": "Terms & Conditions:", "x_min": 50, "x_max": 250, "y": 760},
        {"text": "1. Goods once sold will not be returned.", "x_min": 50, "x_max": 420, "y": 785},
        {"text": "2. Subject to local jurisdiction only.", "x_min": 50, "x_max": 400, "y": 810},

        # Right block (accounting totals)
        {"text": "Sub Total:", "x_min": 650, "x_max": 750, "y": 700},
        {"text": "7580.00", "x_min": 850, "x_max": 950, "y": 700},
        {"text": "CGST @ 9%:", "x_min": 650, "x_max": 770, "y": 730},
        {"text": "682.20", "x_min": 850, "x_max": 950, "y": 730},
        {"text": "SGST @ 9%:", "x_min": 650, "x_max": 770, "y": 760},
        {"text": "682.20", "x_min": 850, "x_max": 950, "y": 760},
        {"text": "Round Off:", "x_min": 650, "x_max": 760, "y": 790},
        {"text": "4.40", "x_min": 850, "x_max": 920, "y": 790},
        {"text": "Grand Total:", "x_min": 650, "x_max": 780, "y": 820},
        {"text": "8990.00", "x_min": 850, "x_max": 950, "y": 820},
    ]

    summary = splitter.split(boxes, doc_width=doc_width)

    # Verify split point is located in the whitespace valley between 450 and 650
    assert 450.0 <= summary.split_x <= 650.0

    # Left narrative fields
    assert summary.amount_in_words is not None
    assert "Eight Thousand Nine Hundred Ninety" in summary.amount_in_words
    assert len(summary.terms_and_conditions) == 2
    assert "Goods once sold" in summary.terms_and_conditions[0]

    # Right accounting totals
    assert summary.subtotal == 7580.0
    assert summary.cgst == 682.20
    assert summary.sgst == 682.20
    assert summary.tax_amount == 1364.40
    assert summary.round_off == 4.40
    assert summary.grand_total == 8990.0


def test_bilateral_splitter_standalone_total():
    """Verify that standalone 'Total:' or 'Total 5000' is recognized as grand total."""
    splitter = BilateralBlockSplitter()
    doc_width = 1000.0

    boxes = [
        {"text": "Sub Total:", "x_min": 650, "x_max": 750, "y": 700},
        {"text": "4500.00", "x_min": 850, "x_max": 950, "y": 700},
        {"text": "Total:", "x_min": 650, "x_max": 750, "y": 750},
        {"text": "4500.00", "x_min": 850, "x_max": 950, "y": 750},
    ]

    summary = splitter.split(boxes, doc_width=doc_width)
    assert summary.subtotal == 4500.0
    assert summary.grand_total == 4500.0


def test_bilateral_splitter_left_aligned_receipt():
    """Verify that receipts with left-aligned totals still extract subtotal and grand total."""
    splitter = BilateralBlockSplitter()
    doc_width = 1000.0

    boxes = [
        {"text": "Subtotal: 100.00", "x_min": 50, "x_max": 250, "y": 200},
        {"text": "Total: 100.00", "x_min": 50, "x_max": 250, "y": 250},
    ]

    summary = splitter.split(boxes, doc_width=doc_width)
    assert summary.subtotal == 100.0
    assert summary.grand_total == 100.0


def test_bilateral_splitter_gst_digit_confusion_repair():
    splitter = BilateralBlockSplitter()
    doc_width = 1000.0

    # SGST has OCR typo (082.20 instead of 682.20)
    boxes = [
        {"text": "Sub Total:", "x_min": 650, "x_max": 750, "y": 700},
        {"text": "7580.00", "x_min": 850, "x_max": 950, "y": 700},
        {"text": "CGST @ 9%:", "x_min": 650, "x_max": 770, "y": 730},
        {"text": "682.20", "x_min": 850, "x_max": 950, "y": 730},
        {"text": "SGST @ 9%:", "x_min": 650, "x_max": 770, "y": 760},
        {"text": "082.20", "x_min": 850, "x_max": 950, "y": 760},  # Typo 0 -> 6
        {"text": "Grand Total:", "x_min": 650, "x_max": 780, "y": 820},
        {"text": "8990.00", "x_min": 850, "x_max": 950, "y": 820},
    ]

    summary = splitter.split(boxes, doc_width=doc_width)
    assert summary.cgst == 682.20
    assert summary.sgst == 682.20  # Repaired from 82.20
    assert summary.tax_amount == 1364.40


def test_bilateral_splitter_symmetric_cgst_repair():
    """Verify that when CGST is corrupted (e.g. 082.20) and SGST is intact (682.20), CGST is repaired."""
    splitter = BilateralBlockSplitter()
    doc_width = 1000.0

    boxes = [
        {"text": "Sub Total:", "x_min": 650, "x_max": 750, "y": 700},
        {"text": "7580.00", "x_min": 850, "x_max": 950, "y": 700},
        {"text": "CGST @ 9%:", "x_min": 650, "x_max": 770, "y": 730},
        {"text": "082.20", "x_min": 850, "x_max": 950, "y": 730},  # CGST corrupted
        {"text": "SGST @ 9%:", "x_min": 650, "x_max": 770, "y": 760},
        {"text": "682.20", "x_min": 850, "x_max": 950, "y": 760},
        {"text": "Grand Total:", "x_min": 650, "x_max": 780, "y": 820},
        {"text": "8990.00", "x_min": 850, "x_max": 950, "y": 820},
    ]

    summary = splitter.split(boxes, doc_width=doc_width)
    assert summary.cgst == 682.20  # Symmetrically repaired
    assert summary.sgst == 682.20
    assert summary.tax_amount == 1364.40


def test_bilateral_splitter_with_discount():
    splitter = BilateralBlockSplitter()
    boxes = [
        {"text": "Subtotal:", "x_min": 650, "x_max": 750, "y": 700},
        {"text": "1000.00", "x_min": 850, "x_max": 950, "y": 700},
        {"text": "Discount:", "x_min": 650, "x_max": 750, "y": 730},
        {"text": "100.00", "x_min": 850, "x_max": 950, "y": 730},
        {"text": "Grand Total:", "x_min": 650, "x_max": 780, "y": 760},
        {"text": "900.00", "x_min": 850, "x_max": 950, "y": 760},
    ]
    summary = splitter.split(boxes, doc_width=1000.0)
    assert summary.subtotal == 1000.0
    assert summary.discount == 100.0
    assert summary.grand_total == 900.0


def test_bilateral_splitter_grand_total_words_fallback():
    splitter = BilateralBlockSplitter()
    doc_width = 1000.0

    boxes = [
        {"text": "Amount in Words: INR Five Thousand Only", "x_min": 50, "x_max": 400, "y": 700},
        {"text": "Subtotal:", "x_min": 650, "x_max": 750, "y": 700},
        {"text": "5000.00", "x_min": 850, "x_max": 950, "y": 700},
        {"text": "Grand Total:", "x_min": 650, "x_max": 780, "y": 750},
        {"text": "XXXXX", "x_min": 850, "x_max": 950, "y": 750},  # unreadable
    ]

    summary = splitter.split(boxes, doc_width=doc_width)
    assert summary.subtotal == 5000.0
    assert summary.grand_total == 5000.0  # Recovered from words


def test_bilateral_splitter_empty_input():
    splitter = BilateralBlockSplitter()
    summary = splitter.split([], doc_width=1000.0)
    assert summary.subtotal is None
    assert summary.grand_total is None
    assert len(summary.left_boxes) == 0
    assert len(summary.right_boxes) == 0
