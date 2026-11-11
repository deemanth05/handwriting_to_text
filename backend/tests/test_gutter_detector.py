"""Unit tests for AdaptiveColumnDetector and tabular column extraction."""

import pytest

from backend.app.schemas.document import DocumentType
from backend.app.services.layout.gutter_detector import (
    AdaptiveColumnDetector,
    ColumnInterval,
    ColumnType,
)


def test_detect_3_column_table():
    detector = AdaptiveColumnDetector()
    table_header = [
        {"text": "Description", "x_min": 50, "x_max": 350, "y": 100},
        {"text": "Rate", "x_min": 400, "x_max": 500, "y": 100},
        {"text": "Total", "x_min": 600, "x_max": 750, "y": 100},
    ]
    columns = detector.detect_columns([], table_header_row=table_header, doc_width=800.0)

    assert len(columns) == 3
    assert columns[0].col_type == ColumnType.DESCRIPTION
    assert columns[1].col_type == ColumnType.RATE
    assert columns[2].col_type == ColumnType.TOTAL


def test_detect_5_column_invoice_table():
    detector = AdaptiveColumnDetector()
    table_header = [
        {"text": "S.No", "x_min": 20, "x_max": 60, "y": 100},
        {"text": "Description of Goods", "x_min": 80, "x_max": 400, "y": 100},
        {"text": "Qty", "x_min": 450, "x_max": 520, "y": 100},
        {"text": "Unit Price", "x_min": 560, "x_max": 660, "y": 100},
        {"text": "Total (Rs)", "x_min": 700, "x_max": 850, "y": 100},
    ]
    columns = detector.detect_columns([], table_header_row=table_header, doc_width=900.0)

    assert len(columns) == 5
    assert columns[0].col_type == ColumnType.INDEX
    assert columns[1].col_type == ColumnType.DESCRIPTION
    assert columns[2].col_type == ColumnType.QUANTITY
    assert columns[3].col_type == ColumnType.RATE
    assert columns[4].col_type == ColumnType.TOTAL


def test_detect_5_column_cash_book_table():
    detector = AdaptiveColumnDetector()
    table_header = [
        {"text": "Date", "x_min": 20, "x_max": 60, "y": 100},
        {"text": "Particulars", "x_min": 100, "x_max": 350, "y": 100},
        {"text": "Debit", "x_min": 400, "x_max": 480, "y": 100},
        {"text": "Credit", "x_min": 520, "x_max": 600, "y": 100},
        {"text": "Balance", "x_min": 650, "x_max": 750, "y": 100},
    ]
    columns = detector.detect_columns(
        [],
        table_header_row=table_header,
        doc_width=800.0,
        doc_type=DocumentType.CASH_BOOK,
    )

    assert len(columns) == 5
    assert columns[0].col_type == ColumnType.DATE
    assert columns[1].col_type == ColumnType.DESCRIPTION
    assert columns[2].col_type == ColumnType.DEBIT
    assert columns[3].col_type == ColumnType.CREDIT
    assert columns[4].col_type == ColumnType.BALANCE


def test_detect_6_column_cash_book_with_voucher():
    """Verify 6-column cash book recognizes Voucher column and maps all columns accurately."""
    detector = AdaptiveColumnDetector()
    table_header = [
        {"text": "Date", "x_min": 20, "x_max": 60, "y": 100},
        {"text": "Vr.No", "x_min": 80, "x_max": 140, "y": 100},
        {"text": "Particulars", "x_min": 160, "x_max": 350, "y": 100},
        {"text": "Debit", "x_min": 380, "x_max": 450, "y": 100},
        {"text": "Credit", "x_min": 480, "x_max": 550, "y": 100},
        {"text": "Balance", "x_min": 580, "x_max": 680, "y": 100},
    ]
    columns = detector.detect_columns([], table_header_row=table_header, doc_type=DocumentType.CASH_BOOK, doc_width=700.0)
    assert len(columns) == 6
    assert columns[0].col_type == ColumnType.DATE
    assert columns[1].col_type == ColumnType.VOUCHER
    assert columns[2].col_type == ColumnType.DESCRIPTION
    assert columns[3].col_type == ColumnType.DEBIT
    assert columns[4].col_type == ColumnType.CREDIT
    assert columns[5].col_type == ColumnType.BALANCE

    rows = [
        [
            {"text": "05/03", "x_min": 25, "x_max": 55, "y": 150},
            {"text": "V-1024", "x_min": 85, "x_max": 130, "y": 150},
            {"text": "Office Stationery & Printing", "x_min": 170, "x_max": 340, "y": 150},
            {"text": "45.00", "x_min": 390, "x_max": 440, "y": 150},
            {"text": "155.00", "x_min": 590, "x_max": 650, "y": 150},
        ]
    ]
    items = detector.parse_cash_book_items(rows, columns)
    assert len(items) == 1
    assert items[0]["entry_date"] == "05/03"
    assert items[0]["voucher_no"] == "V-1024"
    assert items[0]["particulars"] == "Office Stationery & Printing"
    assert items[0]["cash_out_debit"] == 45.0
    assert items[0]["running_balance"] == 155.0


def test_parse_invoice_items_math_validation():
    detector = AdaptiveColumnDetector()
    columns = [
        ColumnInterval(col_id=0, col_type=ColumnType.DESCRIPTION, x_start=0, x_end=350),
        ColumnInterval(col_id=1, col_type=ColumnType.QUANTITY, x_start=350, x_end=500),
        ColumnInterval(col_id=2, col_type=ColumnType.RATE, x_start=500, x_end=680),
        ColumnInterval(col_id=3, col_type=ColumnType.TOTAL, x_start=680, x_end=900),
    ]

    rows = [
        [
            {"text": "Heavy PVC Pipes", "x_min": 50, "x_max": 250, "y": 150},
            {"text": "10", "x_min": 400, "x_max": 450, "y": 150},
            {"text": "120.00", "x_min": 550, "x_max": 620, "y": 150},
            {"text": "1200.00", "x_min": 720, "x_max": 820, "y": 150},
        ]
    ]

    items = detector.parse_invoice_items(rows, columns)
    assert len(items) == 1
    assert items[0]["description"] == "Heavy PVC Pipes"
    assert items[0]["quantity"] == 10.0
    assert items[0]["unit_price"] == 120.0
    assert items[0]["line_total"] == 1200.0


def test_parse_invoice_items_missing_quantity_math_recovery():
    """Verify that when quantity is missed by OCR, it is recovered from total / rate."""
    detector = AdaptiveColumnDetector()
    columns = [
        ColumnInterval(col_id=0, col_type=ColumnType.DESCRIPTION, x_start=0, x_end=350),
        ColumnInterval(col_id=1, col_type=ColumnType.QUANTITY, x_start=350, x_end=500),
        ColumnInterval(col_id=2, col_type=ColumnType.RATE, x_start=500, x_end=680),
        ColumnInterval(col_id=3, col_type=ColumnType.TOTAL, x_start=680, x_end=900),
    ]

    rows = [
        [
            {"text": "Finolex 1.5 sq mm copper wire", "x_min": 50, "x_max": 300, "y": 150},
            {"text": "1450.00", "x_min": 550, "x_max": 620, "y": 150},
            {"text": "2900.00", "x_min": 720, "x_max": 820, "y": 150},
        ]
    ]

    items = detector.parse_invoice_items(rows, columns)
    assert len(items) == 1
    assert items[0]["quantity"] == 2.0  # 2900 / 1450
    assert items[0]["unit_price"] == 1450.0
    assert items[0]["line_total"] == 2900.0
    assert "Finolex 1.5 sq mm copper wire" in items[0]["description"]


def test_parse_invoice_items_missing_rate_math_recovery():
    """Verify that when unit price is missed by OCR, it is recovered from total / quantity."""
    detector = AdaptiveColumnDetector()
    columns = [
        ColumnInterval(col_id=0, col_type=ColumnType.DESCRIPTION, x_start=0, x_end=350),
        ColumnInterval(col_id=1, col_type=ColumnType.QUANTITY, x_start=350, x_end=500),
        ColumnInterval(col_id=2, col_type=ColumnType.RATE, x_start=500, x_end=680),
        ColumnInterval(col_id=3, col_type=ColumnType.TOTAL, x_start=680, x_end=900),
    ]

    rows = [
        [
            {"text": "Anchor 3-Pin Multi Plug Top", "x_min": 50, "x_max": 300, "y": 150},
            {"text": "6", "x_min": 380, "x_max": 420, "y": 150},
            {"text": "510.00", "x_min": 720, "x_max": 820, "y": 150},
        ]
    ]

    items = detector.parse_invoice_items(rows, columns)
    assert len(items) == 1
    assert items[0]["quantity"] == 6.0
    assert items[0]["unit_price"] == 85.0  # 510 / 6
    assert items[0]["line_total"] == 510.0
    assert "Anchor 3-Pin Multi Plug Top" in items[0]["description"]


def test_parse_cash_book_items():
    detector = AdaptiveColumnDetector()
    columns = [
        ColumnInterval(col_id=0, col_type=ColumnType.DATE, x_start=0, x_end=100),
        ColumnInterval(col_id=1, col_type=ColumnType.DESCRIPTION, x_start=100, x_end=400),
        ColumnInterval(col_id=2, col_type=ColumnType.DEBIT, x_start=400, x_end=550),
        ColumnInterval(col_id=3, col_type=ColumnType.CREDIT, x_start=550, x_end=700),
        ColumnInterval(col_id=4, col_type=ColumnType.BALANCE, x_start=700, x_end=900),
    ]

    rows = [
        [
            {"text": "01/02", "x_min": 20, "x_max": 60, "y": 100},
            {"text": "Opening Balance", "x_min": 120, "x_max": 260, "y": 100},
            {"text": "200.00", "x_min": 600, "x_max": 660, "y": 100},
            {"text": "200.00", "x_min": 750, "x_max": 820, "y": 100},
        ],
        [
            {"text": "05/02", "x_min": 20, "x_max": 60, "y": 140},
            {"text": "Stationery items", "x_min": 120, "x_max": 260, "y": 140},
            {"text": "35.00", "x_min": 450, "x_max": 510, "y": 140},
            {"text": "165.00", "x_min": 750, "x_max": 820, "y": 140},
        ],
    ]

    items = detector.parse_cash_book_items(rows, columns)
    assert len(items) == 2
    assert items[0]["entry_date"] == "01/02"
    assert items[0]["cash_in_credit"] == 200.0
    assert items[0]["running_balance"] == 200.0

    assert items[1]["entry_date"] == "05/02"
    assert items[1]["cash_out_debit"] == 35.0
    assert items[1]["running_balance"] == 165.0


def test_parse_cash_book_unknown_column_fallback():
    """Verify that when the particulars column was not recognized as DESCRIPTION, text is not dropped."""
    detector = AdaptiveColumnDetector()
    columns = [
        ColumnInterval(col_id=0, col_type=ColumnType.DATE, x_start=0, x_end=100),
        ColumnInterval(col_id=1, col_type=ColumnType.UNKNOWN, x_start=100, x_end=400),
        ColumnInterval(col_id=2, col_type=ColumnType.DEBIT, x_start=400, x_end=600),
        ColumnInterval(col_id=3, col_type=ColumnType.BALANCE, x_start=600, x_end=800),
    ]

    rows = [
        [
            {"text": "02/03", "x_min": 20, "x_max": 80, "y": 100},
            {"text": "Office Cleaning Supplies", "x_min": 120, "x_max": 300, "y": 100},
            {"text": "50.00", "x_min": 450, "x_max": 520, "y": 100},
            {"text": "150.00", "x_min": 650, "x_max": 720, "y": 100},
        ]
    ]

    items = detector.parse_cash_book_items(rows, columns)
    assert len(items) == 1
    assert items[0]["entry_date"] == "02/03"
    assert items[0]["particulars"] == "Office Cleaning Supplies"
    assert items[0]["cash_out_debit"] == 50.0
    assert items[0]["running_balance"] == 150.0


def test_detect_7_column_table():
    """Verify detection on a complex 7-column table (S.No, Description, HSN, Qty, Unit, Rate, Amount)."""
    detector = AdaptiveColumnDetector()
    table_header = [
        {"text": "S.No", "x_min": 10, "x_max": 40, "y": 100},
        {"text": "Item Description", "x_min": 60, "x_max": 250, "y": 100},
        {"text": "HSN/SAC", "x_min": 270, "x_max": 330, "y": 100},
        {"text": "Qty", "x_min": 350, "x_max": 400, "y": 100},
        {"text": "Unit", "x_min": 420, "x_max": 460, "y": 100},
        {"text": "Rate", "x_min": 480, "x_max": 540, "y": 100},
        {"text": "Amount", "x_min": 560, "x_max": 650, "y": 100},
    ]
    columns = detector.detect_columns([], table_header_row=table_header, doc_width=700.0)
    assert len(columns) == 7
    assert columns[0].col_type == ColumnType.INDEX
    assert columns[1].col_type == ColumnType.DESCRIPTION
    assert columns[2].col_type == ColumnType.HSN
    assert columns[3].col_type == ColumnType.QUANTITY
    assert columns[4].col_type == ColumnType.UNIT
    assert columns[5].col_type == ColumnType.RATE
    assert columns[6].col_type == ColumnType.TOTAL


def test_borderless_headerless_projection():
    """Verify 1D horizontal projection discovers columns when table has no header row and wide margins."""
    detector = AdaptiveColumnDetector()
    rows = [
        [
            {"text": "Item A", "x_min": 100, "x_max": 250, "y": 100},
            {"text": "2", "x_min": 320, "x_max": 350, "y": 100},
            {"text": "50.00", "x_min": 420, "x_max": 480, "y": 100},
            {"text": "100.00", "x_min": 550, "x_max": 620, "y": 100},
        ],
        [
            {"text": "Item B with Long Name", "x_min": 100, "x_max": 280, "y": 140},
            {"text": "4", "x_min": 320, "x_max": 350, "y": 140},
            {"text": "25.00", "x_min": 420, "x_max": 480, "y": 140},
            {"text": "100.00", "x_min": 550, "x_max": 620, "y": 140},
        ],
    ]
    # Document width 900 with content between 100 and 620 (significant page margins)
    columns = detector.detect_columns(rows, table_header_row=None, doc_width=900.0)
    assert len(columns) >= 3
    items = detector.parse_invoice_items(rows, columns)
    assert len(items) == 2
    assert items[0]["quantity"] == 2.0
    assert items[0]["line_total"] == 100.0
    assert items[1]["quantity"] == 4.0
    assert items[1]["line_total"] == 100.0
