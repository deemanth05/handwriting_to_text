"""Comprehensive Unit & Integration Tests for Enterprise Accounting Exporters.

Tests:
1. TallyPrimeExporter (Invoice Purchase Voucher & Cash Book Payment/Receipt Vouchers)
2. ExcelReconciliationExporter (Multi-sheet generation, styling, math validation cells)
3. GSTInvoiceExporter (NIC GST E-Invoice v1.1 Schema structure and arithmetic)
4. FastAPI Export Routes (/api/v1/documents/{id}/export/*)
"""

import json
import xml.etree.ElementTree as ET
from io import BytesIO

import openpyxl
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ConsensusRecord, DocumentRecord, GroundTruthRecord
from backend.app.services.exporters import (
    ExcelReconciliationExporter,
    GSTInvoiceExporter,
    TallyPrimeExporter,
)
from backend.app.services.exporters.tally_exporter import format_tally_date


# ==================== TALLY EXPORTER TESTS ====================


def test_tally_date_formatter():
    assert format_tally_date("2026-11-12") == "20261112"
    assert format_tally_date("12/11/2026") == "20261112"
    assert format_tally_date("12-11-26") == "20261112"
    assert format_tally_date("12.11.2026") == "20261112"
    # Fallback doesn't crash
    res = format_tally_date(None)
    assert len(res) == 8 and res.isdigit()


def test_tally_invoice_export():
    doc_data = {
        "document_id": "test-doc-inv-001",
        "document_type": "INVOICE",
        "fields": {
            "vendor_name": {"value": "Mahalaxmi Steel Traders", "confidence": 0.98},
            "invoice_number": {"value": "MST-2026-88", "confidence": 0.95},
            "invoice_date": {"value": "2026-11-10", "confidence": 0.99},
            "subtotal": {"value": 10000.0, "confidence": 0.98},
            "tax_amount": {"value": 1800.0, "confidence": 0.98},
            "discount_amount": {"value": 0.0, "confidence": 0.98},
            "grand_total": {"value": 11800.0, "confidence": 0.99},
        },
        "line_items": [
            {
                "description": {"value": "MS Angle 50x50x6"},
                "quantity": {"value": 10.0},
                "unit_price": {"value": 500.0},
                "line_total": {"value": 5000.0},
            },
            {
                "description": {"value": "MS Flat 40x5"},
                "quantity": {"value": 10.0},
                "unit_price": {"value": 500.0},
                "line_total": {"value": 5000.0},
            },
        ],
    }

    exporter = TallyPrimeExporter()
    xml_str = exporter.export(doc_data)

    # 1. Must be valid XML
    root = ET.fromstring(xml_str)
    assert root.tag == "ENVELOPE"

    # 2. Check Request & Voucher elements
    request_type = root.find(".//TALLYREQUEST").text
    assert request_type == "Import Data"

    voucher = root.find(".//VOUCHER")
    assert voucher is not None
    assert voucher.attrib["VCHTYPE"] == "Purchase"
    assert voucher.find("VOUCHERNUMBER").text == "MST-2026-88"
    assert voucher.find("PARTYLEDGERNAME").text == "Mahalaxmi Steel Traders"
    assert voucher.find("DATE").text == "20261110"

    # 3. Check balanced double-entry accounting (Sum of debits + credits = 0)
    entries = voucher.findall("ALLLEDGERENTRIES.LIST")
    assert len(entries) >= 4  # Party (Credit), Purchase (Debit), CGST (Debit), SGST (Debit)

    amounts = [float(e.find("AMOUNT").text) for e in entries]
    # In Tally XML: Credit is positive (+11800), Debits are negative (-10000, -900, -900)
    total_balance = sum(amounts)
    assert abs(total_balance) < 0.01, f"Tally double entry balance mismatch: {total_balance}"

    # 4. Check inventory items
    inv_entries = voucher.findall("ALLINVENTORYENTRIES.LIST")
    assert len(inv_entries) == 2
    item_names = [e.find("STOCKITEMNAME").text for e in inv_entries]
    assert "MS Angle 50x50x6" in item_names
    assert "MS Flat 40x5" in item_names


def test_tally_cash_book_export():
    doc_data = {
        "document_id": "test-doc-cash-002",
        "document_type": "CASH_BOOK",
        "fields": {
            "book_title": {"value": "Daily Petty Cash", "confidence": 0.99},
        },
        "ledger_items": [
            {
                "entry_date": {"value": "2026-11-01"},
                "particulars": {"value": "Office Tea & Snacks"},
                "voucher_no": "VCH-01",
                "cash_out_debit": {"value": 250.0},
                "cash_in_credit": {"value": 0.0},
                "running_balance": {"value": 4750.0},
            },
            {
                "entry_date": {"value": "2026-11-02"},
                "particulars": {"value": "Cash from Head Office"},
                "voucher_no": "VCH-02",
                "cash_out_debit": {"value": 0.0},
                "cash_in_credit": {"value": 5000.0},
                "running_balance": {"value": 9750.0},
            },
        ],
    }

    exporter = TallyPrimeExporter()
    xml_str = exporter.export(doc_data)

    root = ET.fromstring(xml_str)
    vouchers = root.findall(".//VOUCHER")
    assert len(vouchers) == 2

    # First voucher is Payment
    assert vouchers[0].attrib["VCHTYPE"] == "Payment"
    assert vouchers[0].find("DATE").text == "20261101"
    p1_entries = vouchers[0].findall("ALLLEDGERENTRIES.LIST")
    assert len(p1_entries) == 2
    p1_amounts = [float(e.find("AMOUNT").text) for e in p1_entries]
    assert abs(sum(p1_amounts)) < 0.01

    # Second voucher is Receipt
    assert vouchers[1].attrib["VCHTYPE"] == "Receipt"
    assert vouchers[1].find("DATE").text == "20261102"
    p2_entries = vouchers[1].findall("ALLLEDGERENTRIES.LIST")
    assert len(p2_entries) == 2
    p2_amounts = [float(e.find("AMOUNT").text) for e in p2_entries]
    assert abs(sum(p2_amounts)) < 0.01


# ==================== EXCEL EXPORTER TESTS ====================


def test_excel_invoice_export():
    doc_data = {
        "document_id": "test-excel-inv-001",
        "document_type": "INVOICE",
        "overall_confidence": 0.96,
        "status": "PROCESSED",
        "fields": {
            "vendor_name": {"value": "Apex Hardware Corp", "confidence": 0.98},
            "invoice_number": {"value": "APX-101", "confidence": 0.95},
            "invoice_date": {"value": "2026-11-11", "confidence": 0.99},
            "gstin": {"value": "27AAACA1234A1Z5", "confidence": 0.97},
            "subtotal": {"value": 2000.0, "confidence": 0.99},
            "tax_amount": {"value": 360.0, "confidence": 0.95},
            "discount_amount": {"value": 50.0, "confidence": 0.92},
            "grand_total": {"value": 2310.0, "confidence": 0.99},
        },
        "line_items": [
            {
                "description": {"value": "Industrial Bolt M10", "confidence": 0.98},
                "quantity": {"value": 100.0, "confidence": 0.95},
                "unit_price": {"value": 15.0, "confidence": 0.97},
                "line_total": {"value": 1500.0, "confidence": 0.99},
                "row_math_valid": True,
            },
            {
                "description": {"value": "Hex Nut M10", "confidence": 0.70},  # Low confidence highlight
                "quantity": {"value": 100.0, "confidence": 0.90},
                "unit_price": {"value": 5.0, "confidence": 0.95},
                "line_total": {"value": 500.0, "confidence": 0.95},
                "row_math_valid": True,
            },
        ],
        "math_validation": {
            "is_valid": True,
            "discrepancy_amount": 0.0,
            "error_details": [],
        },
        "models_participated": ["ollama_vision", "gemini_flash"],
    }

    exporter = ExcelReconciliationExporter()
    xlsx_bytes = exporter.export(doc_data)
    assert len(xlsx_bytes) > 0

    wb = openpyxl.load_workbook(filename=BytesIO(xlsx_bytes))
    sheet_names = wb.sheetnames
    assert "Audit Summary" in sheet_names
    assert "Itemized Register" in sheet_names
    assert "GST E-Invoice Schedule" in sheet_names

    ws1 = wb["Audit Summary"]
    assert "FINANCIAL EXTRACTION & ARITHMETIC AUDIT SUMMARY" in ws1["A1"].value
    # Grand Total row
    found_gt = False
    for r in range(1, 30):
        if ws1.cell(row=r, column=1).value == "Extracted Grand Total":
            assert "2,310.00" in str(ws1.cell(row=r, column=2).value)
            found_gt = True
            break
    assert found_gt

    ws2 = wb["Itemized Register"]
    # Check that rows exist
    assert ws2.cell(row=2, column=2).value == "Industrial Bolt M10"
    assert ws2.cell(row=3, column=2).value == "Hex Nut M10"

    ws3 = wb["GST E-Invoice Schedule"]
    assert ws3.cell(row=2, column=5).value == "27AAACA1234A1Z5"
    assert float(ws3.cell(row=2, column=7).value) == 2000.0


def test_excel_cash_book_export():
    doc_data = {
        "document_id": "test-excel-cb-002",
        "document_type": "CASH_BOOK",
        "overall_confidence": 0.92,
        "status": "PROCESSED",
        "fields": {
            "book_title": {"value": "Shop Khata", "confidence": 0.95},
        },
        "ledger_items": [
            {
                "entry_date": {"value": "2026-11-05", "confidence": 0.95},
                "particulars": {"value": "Courier charges", "confidence": 0.90},
                "voucher_no": "001",
                "cash_out_debit": {"value": 150.0, "confidence": 0.95},
                "cash_in_credit": {"value": 0.0, "confidence": 1.0},
                "running_balance": {"value": 1850.0, "confidence": 0.95},
                "balance_math_valid": True,
            }
        ],
        "math_validation": {"is_valid": True, "discrepancy_amount": 0.0, "error_details": []},
        "models_participated": ["local_surya", "ollama_vision"],
    }

    exporter = ExcelReconciliationExporter()
    xlsx_bytes = exporter.export(doc_data)
    wb = openpyxl.load_workbook(filename=BytesIO(xlsx_bytes))
    assert "Ledger Audit Summary" in wb.sheetnames
    assert "Transactions Register" in wb.sheetnames


# ==================== GST JSON EXPORTER TESTS ====================


def test_gst_invoice_export():
    doc_data = {
        "document_id": "test-gst-001",
        "document_type": "INVOICE",
        "fields": {
            "vendor_name": {"value": "Reliance Retail Ltd", "confidence": 0.99},
            "gstin": {"value": "27AABCR1234B1Z1", "confidence": 0.99},
            "invoice_number": {"value": "RRL-2026-554", "confidence": 0.98},
            "invoice_date": {"value": "2026-11-09", "confidence": 0.99},
            "subtotal": {"value": 5000.0, "confidence": 0.99},
            "tax_amount": {"value": 900.0, "confidence": 0.99},
            "discount_amount": {"value": 0.0, "confidence": 0.99},
            "grand_total": {"value": 5900.0, "confidence": 0.99},
        },
        "line_items": [
            {
                "description": {"value": "LED Tube Light 20W"},
                "hsn_code": {"value": "8539"},
                "quantity": {"value": 25.0},
                "unit_price": {"value": 200.0},
                "line_total": {"value": 5000.0},
            }
        ],
    }

    exporter = GSTInvoiceExporter()
    gst_json = exporter.export(doc_data)

    assert gst_json["Version"] == "1.1"
    assert gst_json["TranDtls"]["TaxSch"] == "GST"
    assert gst_json["DocDtls"]["Typ"] == "INV"
    assert gst_json["DocDtls"]["No"] == "RRL-2026-554"
    assert gst_json["DocDtls"]["Dt"] == "09/11/2026"

    assert gst_json["SellerDtls"]["Gstin"] == "27AABCR1234B1Z1"
    assert gst_json["SellerDtls"]["LglNm"] == "Reliance Retail Ltd"

    assert len(gst_json["ItemList"]) == 1
    item = gst_json["ItemList"][0]
    assert item["PrdDesc"] == "LED Tube Light 20W"
    assert item["HsnCd"] == "8539"
    assert item["TotAmt"] == 5000.0

    assert gst_json["ValDtls"]["AssVal"] == 5000.0
    assert gst_json["ValDtls"]["CgstVal"] == 450.0
    assert gst_json["ValDtls"]["SgstVal"] == 450.0
    assert gst_json["ValDtls"]["TotInvVal"] == 5900.0


# ==================== FASTAPI ROUTES INTEGRATION TESTS ====================


@pytest.mark.asyncio
async def test_export_routes_tally_and_excel(client: AsyncClient, db_session: AsyncSession):
    # 1. Insert sample document record and consensus record
    doc = DocumentRecord(
        id="doc-export-test-123",
        filename="vendor_bill_nov2026.pdf",
        content_type="application/pdf",
        document_type="INVOICE",
        overall_confidence=0.95,
        math_valid=True,
        status="PROCESSED",
    )
    db_session.add(doc)

    cons_payload = {
        "document_id": "doc-export-test-123",
        "document_type": "INVOICE",
        "overall_confidence": 0.95,
        "status": "PROCESSED",
        "fields": {
            "vendor_name": {"value": "Bharat Electronics", "confidence": 0.99},
            "invoice_number": {"value": "BE-9912", "confidence": 0.96},
            "invoice_date": {"value": "2026-11-08", "confidence": 0.99},
            "subtotal": {"value": 8000.0, "confidence": 0.98},
            "tax_amount": {"value": 1440.0, "confidence": 0.98},
            "discount_amount": {"value": 0.0, "confidence": 0.98},
            "grand_total": {"value": 9440.0, "confidence": 0.99},
        },
        "line_items": [
            {
                "description": {"value": "Resistor 10k pack"},
                "quantity": {"value": 10.0},
                "unit_price": {"value": 800.0},
                "line_total": {"value": 8000.0},
            }
        ],
        "math_validation": {"is_valid": True, "discrepancy_amount": 0.0, "error_details": []},
        "models_participated": ["ollama_vision"],
    }

    consensus_rec = ConsensusRecord(
        document_id="doc-export-test-123",
        reconciled_json=json.dumps(cons_payload),
        math_validation_json=json.dumps(cons_payload["math_validation"]),
    )
    db_session.add(consensus_rec)
    await db_session.commit()

    # Test Tally XML export
    res_tally = await client.get("/api/v1/documents/doc-export-test-123/export/tally")
    assert res_tally.status_code == 200
    assert "application/xml" in res_tally.headers["content-type"]
    assert "vendor_bill_nov2026_tally.xml" in res_tally.headers["content-disposition"]
    assert "<TALLYREQUEST>Import Data</TALLYREQUEST>" in res_tally.text
    assert "Bharat Electronics" in res_tally.text

    # Test Excel .xlsx export
    res_excel = await client.get("/api/v1/documents/doc-export-test-123/export/excel")
    assert res_excel.status_code == 200
    assert "spreadsheetml.sheet" in res_excel.headers["content-type"]
    assert "vendor_bill_nov2026_reconciled.xlsx" in res_excel.headers["content-disposition"]
    # Openpyxl load
    wb = openpyxl.load_workbook(filename=BytesIO(res_excel.content))
    assert "Audit Summary" in wb.sheetnames

    # Test GST JSON export
    res_gst = await client.get("/api/v1/documents/doc-export-test-123/export/gst")
    assert res_gst.status_code == 200
    assert "application/json" in res_gst.headers["content-type"]
    assert "vendor_bill_nov2026_gst_einvoice.json" in res_gst.headers["content-disposition"]
    gst_data = res_gst.json()
    assert gst_data["Version"] == "1.1"
    assert gst_data["DocDtls"]["No"] == "BE-9912"


@pytest.mark.asyncio
async def test_export_with_ground_truth_precedence(client: AsyncClient, db_session: AsyncSession):
    # Test that human verification overrides raw AI consensus
    doc = DocumentRecord(
        id="doc-gt-override-456",
        filename="handwritten_note.jpg",
        content_type="image/jpeg",
        document_type="INVOICE",
        overall_confidence=0.70,
        math_valid=False,
        status="NEEDS_REVIEW",
    )
    db_session.add(doc)

    # Initial flawed consensus
    cons_payload = {
        "document_id": "doc-gt-override-456",
        "document_type": "INVOICE",
        "fields": {
            "vendor_name": {"value": "Bad Read Vendor", "confidence": 0.50},
            "grand_total": {"value": 100.0, "confidence": 0.40},
        },
        "line_items": [],
        "math_validation": {"is_valid": False, "discrepancy_amount": 50.0, "error_details": ["Mismatch"]},
    }
    db_session.add(
        ConsensusRecord(
            document_id="doc-gt-override-456",
            reconciled_json=json.dumps(cons_payload),
            math_validation_json=json.dumps(cons_payload["math_validation"]),
        )
    )

    # Human saves verified ground truth
    gt_payload = {
        "fields": {
            "vendor_name": "Verified Golden Hardware",
            "grand_total": 500.0,
            "subtotal": 500.0,
            "tax_amount": 0.0,
        },
        "line_items": [
            {
                "description": "Premium Brass Hinges",
                "quantity": 5.0,
                "unit_price": 100.0,
                "line_total": 500.0,
            }
        ],
        "ledger_items": [],
    }
    db_session.add(
        GroundTruthRecord(
            document_id="doc-gt-override-456",
            ground_truth_json=json.dumps(gt_payload),
            verified_by="expert_accountant",
        )
    )
    await db_session.commit()

    # Now export to Tally - it must use "Verified Golden Hardware" and 500.0
    res_tally = await client.get("/api/v1/documents/doc-gt-override-456/export/tally")
    assert res_tally.status_code == 200
    assert "Verified Golden Hardware" in res_tally.text
    assert "Premium Brass Hinges" in res_tally.text
    assert "Bad Read Vendor" not in res_tally.text


@pytest.mark.asyncio
async def test_export_nonexistent_doc_returns_404(client: AsyncClient):
    res = await client.get("/api/v1/documents/non-existent-id/export/tally")
    assert res.status_code == 404
