"""Unit tests for DocumentMacroZoner (Header, Table, Summary, and Footer separation)."""

from pathlib import Path
import cv2
import pytest
from rapidocr_onnxruntime import RapidOCR

from backend.app.schemas.document import DocumentType
from backend.app.services.layout.zoner import DocumentMacroZoner


def test_zoner_standardize_boxes():
    zoner = DocumentMacroZoner()

    # 1. RapidOCR format: [box, text, score]
    rapid_box = [[[10, 20], [50, 20], [50, 40], [10, 40]], "Sample Text", 0.95]
    std = zoner.standardize_boxes([rapid_box])
    assert len(std) == 1
    assert std[0]["text"] == "Sample Text"
    assert std[0]["x_min"] == 10
    assert std[0]["x_max"] == 50
    assert std[0]["y"] == 30.0

    # 2. Surya format with bbox: [x_min, y_min, x_max, y_max]
    surya_box = {"text": "Surya Text", "bbox": [15, 25, 60, 45], "confidence": 0.90}
    std = zoner.standardize_boxes([surya_box])
    assert len(std) == 1
    assert std[0]["text"] == "Surya Text"
    assert std[0]["x_min"] == 15
    assert std[0]["x_max"] == 60

    # 3. Surya BlockOCRResult format with html
    class FakeBlock:
        html = "<p>HTML Block Text &amp; More</p>"
        confidence = 0.92
        bbox = [20, 30, 80, 50]

    std_block = zoner.standardize_boxes([FakeBlock()])
    assert len(std_block) == 1
    assert std_block[0]["text"] == "HTML Block Text & More"
    assert std_block[0]["x_min"] == 20
    assert std_block[0]["x_max"] == 80


def test_zoner_invoice_macro_zones():
    zoner = DocumentMacroZoner()
    boxes = [
        # Header Zone
        {"text": "Shree Ganesh Electricals", "x_min": 100, "x_max": 400, "y": 30},
        {"text": "GSTIN: 27AAAAA0000A1Z5", "x_min": 100, "x_max": 350, "y": 60},
        {"text": "Invoice No: INV-1024", "x_min": 100, "x_max": 300, "y": 90},
        {"text": "Date: 12/03/2026", "x_min": 500, "x_max": 650, "y": 90},

        # Table Header Row
        {"text": "S.No", "x_min": 50, "x_max": 90, "y": 140},
        {"text": "Description", "x_min": 100, "x_max": 350, "y": 140},
        {"text": "Qty", "x_min": 400, "x_max": 450, "y": 140},
        {"text": "Rate", "x_min": 500, "x_max": 580, "y": 140},
        {"text": "Total", "x_min": 650, "x_max": 750, "y": 140},

        # Table Data Rows (2 items)
        {"text": "1", "x_min": 50, "x_max": 70, "y": 180},
        {"text": "LED Tube Light 20W", "x_min": 100, "x_max": 300, "y": 180},
        {"text": "5", "x_min": 410, "x_max": 430, "y": 180},
        {"text": "250.00", "x_min": 520, "x_max": 570, "y": 180},
        {"text": "1250.00", "x_min": 670, "x_max": 730, "y": 180},

        {"text": "2", "x_min": 50, "x_max": 70, "y": 220},
        {"text": "Copper Wire Roll 90m", "x_min": 100, "x_max": 320, "y": 220},
        {"text": "2", "x_min": 410, "x_max": 430, "y": 220},
        {"text": "1500.00", "x_min": 510, "x_max": 570, "y": 220},
        {"text": "3000.00", "x_min": 670, "x_max": 730, "y": 220},

        # Summary Zone (Left: terms & words, Right: totals)
        {"text": "Amount Chargeable: Four Thousand Two Hundred Fifty Only", "x_min": 50, "x_max": 400, "y": 300},
        {"text": "Sub Total:", "x_min": 500, "x_max": 600, "y": 300},
        {"text": "4250.00", "x_min": 670, "x_max": 740, "y": 300},
        {"text": "Grand Total:", "x_min": 500, "x_max": 620, "y": 340},
        {"text": "4250.00", "x_min": 670, "x_max": 740, "y": 340},

        # Footer Zone
        {"text": "Authorized Signatory", "x_min": 550, "x_max": 750, "y": 420},
    ]

    zones = zoner.zone(boxes, doc_type=DocumentType.INVOICE, doc_width=800.0, doc_height=500.0)

    # Header check
    assert len(zones.header_boxes) == 4
    header_texts = [b["text"] for b in zones.header_boxes]
    assert "Shree Ganesh Electricals" in header_texts

    # Table Header Row
    assert zones.table_header_row is not None
    table_header_texts = [b["text"] for b in zones.table_header_row]
    assert "Description" in table_header_texts
    assert "Qty" in table_header_texts

    # Table Data Rows
    assert len(zones.table_rows) == 2
    row1_texts = [b["text"] for b in zones.table_rows[0]]
    assert "LED Tube Light 20W" in row1_texts

    # Summary Zone
    assert len(zones.summary_boxes) >= 4
    assert zones.bilateral_summary is not None
    assert zones.bilateral_summary.subtotal == 4250.0
    assert zones.bilateral_summary.grand_total == 4250.0

    # Footer Zone
    assert len(zones.footer_boxes) == 1
    assert "Authorized Signatory" in zones.footer_boxes[0]["text"]


def test_zoner_headerless_invoice():
    """Verify that when an invoice has no column header row, top metadata is not lost."""
    zoner = DocumentMacroZoner()
    boxes = [
        {"text": "Quick Print Store", "x_min": 50, "x_max": 250, "y": 40},
        {"text": "Date: 15/03/2026", "x_min": 50, "x_max": 200, "y": 70},
        {"text": "Color A4 Prints", "x_min": 50, "x_max": 250, "y": 120},
        {"text": "10", "x_min": 300, "x_max": 330, "y": 120},
        {"text": "10.00", "x_min": 400, "x_max": 450, "y": 120},
        {"text": "100.00", "x_min": 500, "x_max": 560, "y": 120},
        {"text": "Total:", "x_min": 400, "x_max": 460, "y": 170},
        {"text": "100.00", "x_min": 500, "x_max": 560, "y": 170},
    ]

    zones = zoner.zone(boxes, doc_type=DocumentType.INVOICE, doc_width=600.0, doc_height=300.0)
    assert len(zones.header_boxes) >= 2
    header_texts = [b["text"] for b in zones.header_boxes]
    assert "Quick Print Store" in header_texts
    assert "Date: 15/03/2026" in header_texts

    # Table rows should only contain the line item, NOT the Total row!
    assert len(zones.table_rows) == 1
    assert "Color A4 Prints" in [b["text"] for b in zones.table_rows[0]]
    assert zones.bilateral_summary.grand_total == 100.0


def test_zoner_total_row_not_in_table_rows():
    """Verify that standalone Total row is never treated as a line item."""
    zoner = DocumentMacroZoner()
    boxes = [
        {"text": "Item A", "x_min": 50, "x_max": 200, "y": 100},
        {"text": "2", "x_min": 250, "x_max": 270, "y": 100},
        {"text": "100.00", "x_min": 350, "x_max": 420, "y": 100},
        {"text": "Total 200.00", "x_min": 300, "x_max": 450, "y": 140},
    ]
    zones = zoner.zone(boxes, doc_type=DocumentType.INVOICE, doc_width=500.0, doc_height=200.0)
    assert len(zones.table_rows) == 1
    assert len(zones.summary_boxes) == 1
    assert zones.bilateral_summary.grand_total == 200.0


def test_zoner_real_handwritten_invoice():
    """Verify macro-zoning on real sample_dataset/real_handwritten_invoice.jpg."""
    img_path = Path(__file__).resolve().parents[2] / "sample_dataset" / "real_handwritten_invoice.jpg"
    if not img_path.exists():
        pytest.skip(f"Test file not found: {img_path}")

    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    engine = RapidOCR()
    results, _ = engine(img)

    zoner = DocumentMacroZoner()
    zones = zoner.zone(results, doc_type=DocumentType.INVOICE, doc_width=w, doc_height=h)

    # 1. Header detected
    assert len(zones.header_boxes) > 0
    header_str = " ".join(b["text"] for b in zones.header_boxes)
    assert "BALAJI" in header_str.upper()

    # 2. Table Header Row detected
    assert zones.table_header_row is not None
    hdr_texts = [b["text"] for b in zones.table_header_row]
    assert any("QTY" in t.upper() for t in hdr_texts)
    assert any("RATE" in t.upper() for t in hdr_texts)

    # 3. CRITICAL: Table Rows count must be EXACTLY 7!
    # No false line items (rows 8-11) created from the summary box!
    assert len(zones.table_rows) == 7

    # 4. Summary boxes must capture Subtotal, CGST, SGST, Grand Total
    assert zones.bilateral_summary is not None
    assert zones.bilateral_summary.subtotal == 7580.0
    assert zones.bilateral_summary.cgst == 682.20
    assert zones.bilateral_summary.sgst == 682.20
    assert zones.bilateral_summary.grand_total == 8990.0
    assert "Thousand Nine Hundred Ninety" in (zones.bilateral_summary.amount_in_words or "")

    # 5. Footer boxes must capture signature area
    assert len(zones.footer_boxes) >= 1
    footer_str = " ".join(b["text"] for b in zones.footer_boxes)
    assert any(k in footer_str.lower() for k in ["signature", "kolhapur", "patil", "balaji"])


def test_zoner_empty_boxes():
    zoner = DocumentMacroZoner()
    zones = zoner.zone([])
    assert len(zones.header_boxes) == 0
    assert zones.table_header_row is None
    assert len(zones.table_rows) == 0
    assert len(zones.summary_boxes) == 0
