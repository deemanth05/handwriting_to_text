"""Excel Reconciliation Exporter.

Uses openpyxl to generate multi-sheet corporate financial audit workbooks:
- Sheet 1: Audit Summary & Math Reconciliation (Deterministic Integrity Checks)
- Sheet 2: Itemized Line / Ledger Register (Confidence-highlighted cells)
- Sheet 3: GSTR-2B / GST E-Invoice Compliance Schedule
"""

from __future__ import annotations

import io
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


class ExcelReconciliationExporter:
    """Generate multi-sheet styled Excel workbooks for financial document extractions."""

    def __init__(self):
        # Color palette
        self.header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        self.header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        self.sub_header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        self.sub_header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")

        self.pass_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        self.pass_font = Font(name="Segoe UI", size=10, bold=True, color="166534")

        self.warn_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
        self.warn_font = Font(name="Segoe UI", size=10, bold=True, color="854D0E")

        self.fail_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        self.fail_font = Font(name="Segoe UI", size=10, bold=True, color="991B1B")

        self.thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        self.bold_font = Font(name="Segoe UI", size=10, bold=True)
        self.regular_font = Font(name="Segoe UI", size=10)

    def export(self, doc_data: dict[str, Any]) -> bytes:
        """Export document data to in-memory Excel workbook bytes."""
        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        doc_type = doc_data.get("document_type", "INVOICE").upper()
        if doc_type in ["CASH_BOOK", "KHATA_LEDGER"]:
            self._build_ledger_sheets(wb, doc_data)
        else:
            self._build_invoice_sheets(wb, doc_data)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    def _auto_fit_columns(self, ws):
        """Auto-adjust worksheet column widths with padding."""
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    def _build_invoice_sheets(self, wb: openpyxl.Workbook, doc: dict[str, Any]):
        fields = doc.get("fields", {})

        def get_val(key, default=""):
            f = fields.get(key)
            if f is None and key in doc:
                f = doc.get(key)
            if isinstance(f, dict):
                return f.get("value", default)
            return f if f is not None else default

        vendor = get_val("vendor_name", "N/A")
        inv_no = get_val("invoice_number", "N/A")
        inv_date = get_val("invoice_date", "N/A")
        subtotal = float(get_val("subtotal", 0.0) or 0.0)
        tax = float(get_val("tax_amount", 0.0) or 0.0)
        discount = float(get_val("discount_amount", 0.0) or 0.0)
        grand_total = float(get_val("grand_total", 0.0) or (subtotal + tax - discount))
        gstin = get_val("gstin", "27AABCS1429B1Z2")

        math_val = doc.get("math_validation", {})
        is_math_valid = math_val.get("is_valid", True)
        discrepancy = math_val.get("discrepancy_amount", 0.0)
        math_errors = math_val.get("error_details", [])

        # ==================== SHEET 1: AUDIT SUMMARY ====================
        ws1 = wb.create_sheet(title="Audit Summary")
        ws1.views.sheetView[0].showGridLines = True

        # Header Title
        ws1.merge_cells("A1:D1")
        top_cell = ws1["A1"]
        top_cell.value = "FINANCIAL EXTRACTION & ARITHMETIC AUDIT SUMMARY"
        top_cell.font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
        top_cell.fill = self.header_fill
        top_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws1.row_dimensions[1].height = 35

        # Document Details
        metadata = [
            ("Document ID", doc.get("document_id", "N/A")),
            ("Document Type", doc.get("document_type", "INVOICE")),
            ("Processing Status", doc.get("status", "PROCESSED")),
            ("Vendor / Supplier Name", vendor),
            ("Invoice Number", inv_no),
            ("Invoice Date", inv_date),
            ("Supplier GSTIN", gstin),
            ("Overall Model Confidence", f"{doc.get('overall_confidence', 0.0) * 100:.1f}%"),
            ("Participating Engines", ", ".join(doc.get("models_participated", []))),
        ]

        curr_r = 3
        ws1.cell(row=curr_r, column=1, value="DOCUMENT METADATA").font = self.bold_font
        curr_r += 1

        for label, val in metadata:
            c1 = ws1.cell(row=curr_r, column=1, value=label)
            c2 = ws1.cell(row=curr_r, column=2, value=val)
            c1.font = self.bold_font
            c2.font = self.regular_font
            c1.border = self.thin_border
            c2.border = self.thin_border
            curr_r += 1

        # Arithmetic Reconciliation Section
        curr_r += 1
        ws1.cell(row=curr_r, column=1, value="DETERMINISTIC ARITHMETIC AUDIT").font = self.bold_font
        curr_r += 1

        calc_rows = [
            ("Extracted Subtotal (Taxable)", f"₹ {subtotal:,.2f}"),
            ("Extracted Tax (CGST + SGST)", f"₹ {tax:,.2f}"),
            ("Extracted Discount", f"₹ {discount:,.2f}"),
            ("Extracted Grand Total", f"₹ {grand_total:,.2f}"),
            ("Arithmetic Discrepancy", f"₹ {discrepancy:,.2f}"),
            ("Deterministic Math Status", "PASSED (Zero-Variance)" if is_math_valid else "AUDIT REQUIRED"),
        ]

        for label, val in calc_rows:
            c1 = ws1.cell(row=curr_r, column=1, value=label)
            c2 = ws1.cell(row=curr_r, column=2, value=val)
            c1.font = self.bold_font
            c2.font = self.regular_font
            c1.border = self.thin_border
            c2.border = self.thin_border

            if "Math Status" in label:
                if is_math_valid:
                    c2.fill = self.pass_fill
                    c2.font = self.pass_font
                else:
                    c2.fill = self.fail_fill
                    c2.font = self.fail_font
            curr_r += 1

        if math_errors:
            curr_r += 1
            ws1.cell(row=curr_r, column=1, value="Discrepancy Details:").font = self.bold_font
            curr_r += 1
            for err in math_errors:
                c = ws1.cell(row=curr_r, column=1, value=f"• {err}")
                c.font = self.fail_font
                curr_r += 1

        self._auto_fit_columns(ws1)

        # ==================== SHEET 2: ITEMIZED REGISTER ====================
        ws2 = wb.create_sheet(title="Itemized Register")
        ws2.views.sheetView[0].showGridLines = True

        headers = ["Row ID", "Item Description", "Quantity", "Unit Price (₹)", "Line Total (₹)", "Math Valid", "Confidence", "Page"]
        ws2.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws2.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self.thin_border
        ws2.row_dimensions[1].height = 28

        line_items = doc.get("line_items", [])
        for idx, it in enumerate(line_items, 1):
            def extract_val(d, k, def_val):
                v = d.get(k)
                if isinstance(v, dict):
                    return v.get("value", def_val)
                return v if v is not None else def_val

            def extract_conf(d, k):
                v = d.get(k)
                if isinstance(v, dict):
                    return float(v.get("confidence", 0.90) or 0.90)
                return 0.90

            desc = extract_val(it, "description", f"Item {idx}")
            qty = float(extract_val(it, "quantity", 1.0) or 1.0)
            rate = float(extract_val(it, "unit_price", 0.0) or 0.0)
            tot = float(extract_val(it, "line_total", 0.0) or (qty * rate))
            math_ok = it.get("row_math_valid", True)
            conf = extract_conf(it, "description")
            page_num = it.get("page_number", 1)

            row_cells = [
                idx,
                desc,
                qty,
                round(rate, 2),
                round(tot, 2),
                "VALID" if math_ok else "DISCREPANCY",
                f"{conf * 100:.0f}%",
                f"p.{page_num}",
            ]
            ws2.append(row_cells)
            r_idx = ws2.max_row

            # Apply borders and formats
            for c_idx in range(1, len(headers) + 1):
                c = ws2.cell(row=r_idx, column=c_idx)
                c.font = self.regular_font
                c.border = self.thin_border
                if c_idx in [3, 4, 5]:
                    c.alignment = Alignment(horizontal="right")
                if c_idx == 6:
                    c.alignment = Alignment(horizontal="center")
                    c.fill = self.pass_fill if math_ok else self.fail_fill
                    c.font = self.pass_font if math_ok else self.fail_font
                if c_idx == 7:
                    c.alignment = Alignment(horizontal="center")
                    if conf >= 0.85:
                        c.fill = self.pass_fill
                        c.font = self.pass_font
                    elif conf >= 0.70:
                        c.fill = self.warn_fill
                        c.font = self.warn_font
                    else:
                        c.fill = self.fail_fill
                        c.font = self.fail_font

        self._auto_fit_columns(ws2)

        # ==================== SHEET 3: GST FILING SCHEDULE ====================
        ws3 = wb.create_sheet(title="GST E-Invoice Schedule")
        ws3.views.sheetView[0].showGridLines = True

        gst_headers = [
            "Supply Type",
            "Document Type",
            "Document Number",
            "Document Date",
            "Supplier GSTIN",
            "Supplier Legal Name",
            "Taxable Value (₹)",
            "CGST Amount (₹)",
            "SGST Amount (₹)",
            "IGST Amount (₹)",
            "Total Invoice Value (₹)",
        ]
        ws3.append(gst_headers)
        for col_idx in range(1, len(gst_headers) + 1):
            cell = ws3.cell(row=1, column=col_idx)
            cell.font = self.sub_header_font
            cell.fill = self.sub_header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self.thin_border
        ws3.row_dimensions[1].height = 25

        cgst = round(tax / 2.0, 2)
        sgst = round(tax - cgst, 2)

        ws3.append([
            "B2B",
            "INV",
            inv_no,
            inv_date,
            gstin,
            vendor,
            round(subtotal, 2),
            round(cgst, 2),
            round(sgst, 2),
            0.0,
            round(grand_total, 2),
        ])

        for c_idx in range(1, len(gst_headers) + 1):
            c = ws3.cell(row=2, column=c_idx)
            c.font = self.regular_font
            c.border = self.thin_border
            if c_idx >= 7:
                c.alignment = Alignment(horizontal="right")

        self._auto_fit_columns(ws3)

    def _build_ledger_sheets(self, wb: openpyxl.Workbook, doc: dict[str, Any]):
        fields = doc.get("fields", {})

        def get_val(key, default=""):
            f = fields.get(key)
            if f is None and key in doc:
                f = doc.get(key)
            if isinstance(f, dict):
                return f.get("value", default)
            return f if f is not None else default

        book_title = get_val("book_title") or get_val("customer_name") or "Petty Cash Book"
        open_bal = float(get_val("opening_balance", 0.0) or 0.0)
        close_bal = float(get_val("closing_balance", 0.0) or 0.0)
        period = get_val("period", "N/A")

        # ==================== SHEET 1: LEDGER SUMMARY ====================
        ws1 = wb.create_sheet(title="Ledger Audit Summary")
        ws1.views.sheetView[0].showGridLines = True

        ws1.merge_cells("A1:D1")
        top_cell = ws1["A1"]
        top_cell.value = "LEDGER & CASH BOOK AUDIT SUMMARY"
        top_cell.font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
        top_cell.fill = self.header_fill
        top_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws1.row_dimensions[1].height = 35

        metadata = [
            ("Document ID", doc.get("document_id", "N/A")),
            ("Document Type", doc.get("document_type", "CASH_BOOK")),
            ("Ledger / Account Title", book_title),
            ("Accounting Period", period),
            ("Opening Balance", f"₹ {open_bal:,.2f}"),
            ("Closing Balance", f"₹ {close_bal:,.2f}"),
            ("Overall Confidence", f"{doc.get('overall_confidence', 0.0) * 100:.1f}%"),
            ("Math Validation", "PASSED" if doc.get("math_validation", {}).get("is_valid", True) else "REVIEW REQUIRED"),
        ]

        curr_r = 3
        for label, val in metadata:
            c1 = ws1.cell(row=curr_r, column=1, value=label)
            c2 = ws1.cell(row=curr_r, column=2, value=val)
            c1.font = self.bold_font
            c2.font = self.regular_font
            c1.border = self.thin_border
            c2.border = self.thin_border
            curr_r += 1

        self._auto_fit_columns(ws1)

        # ==================== SHEET 2: CASH TRANSACTIONS ====================
        ws2 = wb.create_sheet(title="Transactions Register")
        ws2.views.sheetView[0].showGridLines = True

        headers = ["Row ID", "Entry Date", "Particulars / Narration", "Voucher No", "Cash Out (Dr)", "Cash In (Cr)", "Running Balance", "Math Valid", "Confidence", "Page"]
        ws2.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws2.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self.thin_border
        ws2.row_dimensions[1].height = 28

        ledger_items = doc.get("ledger_items", [])
        for idx, it in enumerate(ledger_items, 1):
            def extract_val(d, k, def_val):
                v = d.get(k)
                if isinstance(v, dict):
                    return v.get("value", def_val)
                return v if v is not None else def_val

            def extract_conf(d, k):
                v = d.get(k)
                if isinstance(v, dict):
                    return float(v.get("confidence", 0.90) or 0.90)
                return 0.90

            date_val = extract_val(it, "entry_date", "")
            particulars = extract_val(it, "particulars", "")
            voucher_no = extract_val(it, "voucher_no", "")
            out_val = float(extract_val(it, "cash_out_debit", 0.0) or 0.0)
            in_val = float(extract_val(it, "cash_in_credit", 0.0) or 0.0)
            bal_val = float(extract_val(it, "running_balance", 0.0) or 0.0)
            math_ok = it.get("balance_math_valid", True)
            conf = extract_conf(it, "particulars")
            page_num = it.get("page_number", 1)

            row_cells = [
                idx,
                date_val,
                particulars,
                voucher_no,
                round(out_val, 2) if out_val > 0 else "-",
                round(in_val, 2) if in_val > 0 else "-",
                round(bal_val, 2),
                "VALID" if math_ok else "DISCREPANCY",
                f"{conf * 100:.0f}%",
                f"p.{page_num}",
            ]
            ws2.append(row_cells)
            r_idx = ws2.max_row

            for c_idx in range(1, len(headers) + 1):
                c = ws2.cell(row=r_idx, column=c_idx)
                c.font = self.regular_font
                c.border = self.thin_border
                if c_idx in [5, 6, 7]:
                    c.alignment = Alignment(horizontal="right")
                if c_idx == 8:
                    c.alignment = Alignment(horizontal="center")
                    c.fill = self.pass_fill if math_ok else self.fail_fill
                    c.font = self.pass_font if math_ok else self.fail_font
                if c_idx == 9:
                    c.alignment = Alignment(horizontal="center")
                    if conf >= 0.85:
                        c.fill = self.pass_fill
                        c.font = self.pass_font
                    else:
                        c.fill = self.warn_fill
                        c.font = self.warn_font

        self._auto_fit_columns(ws2)
