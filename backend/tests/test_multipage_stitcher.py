"""Unit Tests for Multi-Page Cross-Table Stitcher and Ledger Continuity Service."""

import pytest

from backend.app.schemas.document import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    LedgerTransactionItem,
    LineItem,
    MathValidationResult,
)
from backend.app.services.multipage.stitcher import MultiPageStitcher


def test_single_page_passthrough():
    p1 = DocumentExtractionResponse(
        document_id="doc-single-001",
        document_type=DocumentType.INVOICE,
        overall_confidence=0.95,
        fields={"vendor_name": ExtractedField(value="Alpha Traders", confidence=0.98)},
        line_items=[
            LineItem(
                row_id=1,
                description=ExtractedField(value="Item A"),
                quantity=ExtractedField(value=2.0),
                unit_price=ExtractedField(value=100.0),
                line_total=ExtractedField(value=200.0),
            )
        ],
    )

    stitcher = MultiPageStitcher()
    res = stitcher.stitch("doc-single-001", DocumentType.INVOICE, [p1])

    assert res.page_count == 1
    assert len(res.pages) == 1
    assert res.line_items[0].page_number == 1
    assert res.fields["vendor_name"].value == "Alpha Traders"


def test_multi_page_invoice_stitching_with_cf_bf_filter():
    # Page 1: Has Header, Items 1 & 2, and a C/F row
    p1 = DocumentExtractionResponse(
        document_id="doc-multi-001_p1",
        document_type=DocumentType.INVOICE,
        overall_confidence=0.96,
        fields={
            "vendor_name": ExtractedField(value="Mahalaxmi Electricals", confidence=0.98),
            "invoice_number": ExtractedField(value="ME-2026-901", confidence=0.95),
            "invoice_date": ExtractedField(value="2026-11-12", confidence=0.99),
            "gstin": ExtractedField(value="27AAAPM1234A1Z0", confidence=0.97),
        },
        line_items=[
            LineItem(
                row_id=1,
                description=ExtractedField(value="Copper Wire 2.5mm"),
                quantity=ExtractedField(value=5.0),
                unit_price=ExtractedField(value=1000.0),
                line_total=ExtractedField(value=5000.0),
            ),
            LineItem(
                row_id=2,
                description=ExtractedField(value="Modular Switch 6A"),
                quantity=ExtractedField(value=20.0),
                unit_price=ExtractedField(value=150.0),
                line_total=ExtractedField(value=3000.0),
            ),
            LineItem(
                row_id=3,
                description=ExtractedField(value="Total Carried Forward C/F"),
                quantity=ExtractedField(value=0.0),
                unit_price=ExtractedField(value=0.0),
                line_total=ExtractedField(value=8000.0),
            ),
        ],
    )

    # Page 2: Has B/F row, Item 3, Subtotal, Tax, Grand Total
    p2 = DocumentExtractionResponse(
        document_id="doc-multi-001_p2",
        document_type=DocumentType.INVOICE,
        overall_confidence=0.94,
        fields={
            "subtotal": ExtractedField(value=10000.0, confidence=0.97),
            "tax_amount": ExtractedField(value=1800.0, confidence=0.95),
            "discount_amount": ExtractedField(value=0.0, confidence=0.99),
            "grand_total": ExtractedField(value=11800.0, confidence=0.98),
        },
        line_items=[
            LineItem(
                row_id=1,
                description=ExtractedField(value="Balance Brought Forward B/F"),
                quantity=ExtractedField(value=0.0),
                unit_price=ExtractedField(value=0.0),
                line_total=ExtractedField(value=8000.0),
            ),
            LineItem(
                row_id=2,
                description=ExtractedField(value="MCB Double Pole 32A"),
                quantity=ExtractedField(value=4.0),
                unit_price=ExtractedField(value=500.0),
                line_total=ExtractedField(value=2000.0),
            ),
        ],
    )

    stitcher = MultiPageStitcher()
    stitched = stitcher.stitch("doc-multi-001", DocumentType.INVOICE, [p1, p2])

    assert stitched.page_count == 2
    assert len(stitched.pages) == 2

    # Verify Header inheritance from Page 1
    assert stitched.fields["vendor_name"].value == "Mahalaxmi Electricals"
    assert stitched.fields["invoice_number"].value == "ME-2026-901"
    assert stitched.fields["subtotal"].value == 10000.0
    assert stitched.fields["grand_total"].value == 11800.0

    # Verify C/F and B/F rows were filtered out
    # Only 3 true items should remain: Copper Wire (5000), Modular Switch (3000), MCB (2000) = 10,000!
    assert len(stitched.line_items) == 3

    assert stitched.line_items[0].description.value == "Copper Wire 2.5mm"
    assert stitched.line_items[0].row_id == 1
    assert stitched.line_items[0].page_number == 1

    assert stitched.line_items[1].description.value == "Modular Switch 6A"
    assert stitched.line_items[1].row_id == 2
    assert stitched.line_items[1].page_number == 1

    assert stitched.line_items[2].description.value == "MCB Double Pole 32A"
    assert stitched.line_items[2].row_id == 3
    assert stitched.line_items[2].page_number == 2

    # Verify Global Arithmetic Validation passed
    assert stitched.math_validation.is_valid is True
    assert stitched.math_validation.discrepancy_amount == 0.0
    assert len(stitched.math_validation.error_details) == 0


def test_multi_page_invoice_math_discrepancy_detection():
    # If items sum to 7000 but subtotal is 8000
    p1 = DocumentExtractionResponse(
        document_id="doc-disc-p1",
        document_type=DocumentType.INVOICE,
        overall_confidence=0.90,
        fields={"vendor_name": ExtractedField(value="Test Vendor", confidence=0.90)},
        line_items=[
            LineItem(
                row_id=1,
                description=ExtractedField(value="Item 1"),
                quantity=ExtractedField(value=1.0),
                unit_price=ExtractedField(value=3000.0),
                line_total=ExtractedField(value=3000.0),
            )
        ],
    )
    p2 = DocumentExtractionResponse(
        document_id="doc-disc-p2",
        document_type=DocumentType.INVOICE,
        overall_confidence=0.90,
        fields={
            "subtotal": ExtractedField(value=8000.0, confidence=0.95),  # 3000 + 4000 = 7000 != 8000!
            "grand_total": ExtractedField(value=8000.0, confidence=0.95),
        },
        line_items=[
            LineItem(
                row_id=1,
                description=ExtractedField(value="Item 2"),
                quantity=ExtractedField(value=1.0),
                unit_price=ExtractedField(value=4000.0),
                line_total=ExtractedField(value=4000.0),
            )
        ],
    )

    stitcher = MultiPageStitcher()
    stitched = stitcher.stitch("doc-disc", DocumentType.INVOICE, [p1, p2])

    assert stitched.math_validation.is_valid is False
    assert stitched.math_validation.discrepancy_amount == 1000.0
    assert any("Cross-page line items sum" in err for err in stitched.math_validation.error_details)


def test_multi_page_khata_ledger_continuity():
    # Page 1: Opens at 10000, 2 entries, closes at 7500
    p1 = DocumentExtractionResponse(
        document_id="khata-p1",
        document_type=DocumentType.CASH_BOOK,
        overall_confidence=0.95,
        fields={"book_title": ExtractedField(value="Daily Petty Cash", confidence=0.95)},
        ledger_items=[
            LedgerTransactionItem(
                row_id=1,
                entry_date=ExtractedField(value="2026-11-01"),
                particulars=ExtractedField(value="Stationery"),
                cash_out_debit=ExtractedField(value=1000.0),
                cash_in_credit=ExtractedField(value=0.0),
                running_balance=ExtractedField(value=9000.0),
            ),
            LedgerTransactionItem(
                row_id=2,
                entry_date=ExtractedField(value="2026-11-02"),
                particulars=ExtractedField(value="Postage"),
                cash_out_debit=ExtractedField(value=1500.0),
                cash_in_credit=ExtractedField(value=0.0),
                running_balance=ExtractedField(value=7500.0),
            ),
        ],
    )

    # Page 2: Continues from 7500, +2500 cash in -> 10000
    p2 = DocumentExtractionResponse(
        document_id="khata-p2",
        document_type=DocumentType.CASH_BOOK,
        overall_confidence=0.95,
        ledger_items=[
            LedgerTransactionItem(
                row_id=1,
                entry_date=ExtractedField(value="2026-11-03"),
                particulars=ExtractedField(value="Cash from Bank"),
                cash_out_debit=ExtractedField(value=0.0),
                cash_in_credit=ExtractedField(value=2500.0),
                running_balance=ExtractedField(value=10000.0),
            )
        ],
    )

    stitcher = MultiPageStitcher()
    stitched = stitcher.stitch("khata-doc", DocumentType.CASH_BOOK, [p1, p2])

    assert stitched.page_count == 2
    assert len(stitched.ledger_items) == 3
    assert stitched.ledger_items[0].page_number == 1
    assert stitched.ledger_items[1].page_number == 1
    assert stitched.ledger_items[2].page_number == 2
    assert stitched.ledger_items[2].row_id == 3

    # Continuity holds: 7500 + 2500 = 10000
    assert stitched.math_validation.is_valid is True
    assert stitched.math_validation.discrepancy_amount == 0.0


def test_multi_page_khata_ledger_broken_continuity():
    # Page 1 closes at 7500, but Page 2 erroneously starts at 5000 (discrepancy of 2500)
    p1 = DocumentExtractionResponse(
        document_id="khata-p1",
        document_type=DocumentType.CASH_BOOK,
        overall_confidence=0.95,
        ledger_items=[
            LedgerTransactionItem(
                row_id=1,
                entry_date=ExtractedField(value="2026-11-01"),
                particulars=ExtractedField(value="Expense"),
                cash_out_debit=ExtractedField(value=500.0),
                cash_in_credit=ExtractedField(value=0.0),
                running_balance=ExtractedField(value=7500.0),
            )
        ],
    )
    p2 = DocumentExtractionResponse(
        document_id="khata-p2",
        document_type=DocumentType.CASH_BOOK,
        overall_confidence=0.95,
        ledger_items=[
            LedgerTransactionItem(
                row_id=1,
                entry_date=ExtractedField(value="2026-11-02"),
                particulars=ExtractedField(value="Missing page entry"),
                cash_out_debit=ExtractedField(value=0.0),
                cash_in_credit=ExtractedField(value=1000.0),
                running_balance=ExtractedField(value=6000.0),  # Should be 7500 + 1000 = 8500!
            )
        ],
    )

    stitcher = MultiPageStitcher()
    stitched = stitcher.stitch("khata-doc", DocumentType.CASH_BOOK, [p1, p2])

    assert stitched.math_validation.is_valid is False
    assert stitched.math_validation.discrepancy_amount == 2500.0
    assert any("Cross-page ledger continuity break" in err for err in stitched.math_validation.error_details)
