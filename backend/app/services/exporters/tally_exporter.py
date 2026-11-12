"""Tally Prime XML Exporter.

Converts extracted documents (invoices, cash books, khatas) into official
Tally Prime XML format suitable for 1-click import into Tally ERP / Tally Prime.

Supports:
- Purchase Vouchers with balanced double-entry accounting and inventory allocations
- Cash Payment and Receipt Vouchers for Cash Books / Khatas
- Automated date normalization to Tally's canonical YYYYMMDD format
- Custom ledger name mapping and rounding adjustments
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape


def format_tally_date(date_str: str | None) -> str:
    """Normalize any date string to Tally canonical YYYYMMDD format."""
    if not date_str:
        return datetime.now().strftime("%Y%m%d")

    clean = date_str.strip()

    # Try ISO YYYY-MM-DD
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", clean)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}{int(mo):02d}{int(d):02d}"

    # Try DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", clean)
    if m:
        d, mo, y = m.groups()
        if len(y) == 2:
            y = f"20{y}"
        return f"{int(y):04d}{int(mo):02d}{int(d):02d}"

    # Try DD/MM (assume current year)
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})$", clean)
    if m:
        d, mo = m.groups()
        y = datetime.now().year
        return f"{y:04d}{int(mo):02d}{int(d):02d}"

    return datetime.now().strftime("%Y%m%d")


class TallyPrimeExporter:
    """Export document extraction results to Tally Prime XML import format."""

    def __init__(
        self,
        purchase_ledger: str = "Purchase Account",
        cgst_ledger: str = "Input CGST",
        sgst_ledger: str = "Input SGST",
        igst_ledger: str = "Input IGST",
        round_off_ledger: str = "Round Off",
        cash_ledger: str = "Petty Cash",
        default_party_ledger: str = "Sundry Creditor",
    ):
        self.purchase_ledger = purchase_ledger
        self.cgst_ledger = cgst_ledger
        self.sgst_ledger = sgst_ledger
        self.igst_ledger = igst_ledger
        self.round_off_ledger = round_off_ledger
        self.cash_ledger = cash_ledger
        self.default_party_ledger = default_party_ledger

    def export(self, doc_data: dict[str, Any]) -> str:
        """Main export dispatcher based on document_type."""
        doc_type = doc_data.get("document_type", "INVOICE").upper()

        if doc_type in ["CASH_BOOK", "KHATA_LEDGER"]:
            return self._export_ledger_to_tally(doc_data)
        return self._export_invoice_to_tally(doc_data)

    def _export_invoice_to_tally(self, doc: dict[str, Any]) -> str:
        """Generate Tally Purchase Voucher XML from invoice extraction."""
        fields = doc.get("fields", {})

        def get_field_val(key: str, default=None):
            f = fields.get(key)
            if f is None and key in doc:
                f = doc.get(key)
            if isinstance(f, dict):
                return f.get("value", default)
            return f if f is not None else default

        vendor = get_field_val("vendor_name") or self.default_party_ledger
        inv_no = get_field_val("invoice_number") or f"INV-{doc.get('document_id', '')[:8]}"
        inv_date = get_field_val("invoice_date")
        tally_date = format_tally_date(inv_date)

        subtotal = float(get_field_val("subtotal") or 0.0)
        tax = float(get_field_val("tax_amount") or 0.0)
        discount = float(get_field_val("discount_amount") or 0.0)
        grand_total = float(get_field_val("grand_total") or (subtotal + tax - discount))

        # Infer CGST and SGST split (assume 50/50 intra-state by default)
        cgst_amt = round(tax / 2.0, 2) if tax > 0 else 0.0
        sgst_amt = round(tax - cgst_amt, 2) if tax > 0 else 0.0

        def _get_val(obj, key, default=0.0):
            if isinstance(obj, dict):
                v = obj.get(key)
                if isinstance(v, dict):
                    return v.get("value", default)
                return v if v is not None else default
            return default

        line_items = doc.get("line_items", [])
        if not subtotal and line_items:
            subtotal = sum(float(_get_val(item, "line_total", 0.0) or 0.0) for item in line_items)
            if not grand_total:
                grand_total = subtotal + tax - discount

        # Compute round-off difference
        computed_total = round(subtotal + tax - discount, 2)
        round_off = round(grand_total - computed_total, 2)

        xml_lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<ENVELOPE>",
            "  <HEADER>",
            "    <TALLYREQUEST>Import Data</TALLYREQUEST>",
            "  </HEADER>",
            "  <BODY>",
            "    <IMPORTDATA>",
            "      <REQUESTDESC>",
            "        <REPORTNAME>Vouchers</REPORTNAME>",
            "        <STATICVARIABLES>",
            "          <SVCURRENTCOMPANY>##SVCURRENTCOMPANY</SVCURRENTCOMPANY>",
            "        </STATICVARIABLES>",
            "      </REQUESTDESC>",
            "      <REQUESTDATA>",
            '        <TALLYMESSAGE xmlns:UDF="TallyUDF">',
            f'          <VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Invoice Voucher View">',
            f"            <DATE>{tally_date}</DATE>",
            f"            <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>",
            f"            <VOUCHERNUMBER>{escape(str(inv_no))}</VOUCHERNUMBER>",
            f"            <REFERENCE>{escape(str(inv_no))}</REFERENCE>",
            f"            <REFERENCEDATE>{tally_date}</REFERENCEDATE>",
            f"            <PARTYLEDGERNAME>{escape(str(vendor))}</PARTYLEDGERNAME>",
            f"            <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>",
            f"            <ISINVOICE>Yes</ISINVOICE>",
            f"            <NARRATION>Auto-imported via Paper-to-Structured-Data Engine (Doc ID: {doc.get('document_id', '')})</NARRATION>",
        ]

        # 1. Party Ledger Entry (Credit)
        xml_lines.extend([
            "            <ALLLEDGERENTRIES.LIST>",
            f"              <LEDGERNAME>{escape(str(vendor))}</LEDGERNAME>",
            "              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>",
            "              <ISPARTYLEDGER>Yes</ISPARTYLEDGER>",
            f"              <AMOUNT>{grand_total:.2f}</AMOUNT>",
            "            </ALLLEDGERENTRIES.LIST>",
        ])

        # 2. Purchase Account Ledger Entry (Debit)
        xml_lines.extend([
            "            <ALLLEDGERENTRIES.LIST>",
            f"              <LEDGERNAME>{escape(self.purchase_ledger)}</LEDGERNAME>",
            "              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
            "              <ISPARTYLEDGER>No</ISPARTYLEDGER>",
            f"              <AMOUNT>-{subtotal:.2f}</AMOUNT>",
            "            </ALLLEDGERENTRIES.LIST>",
        ])

        # 3. CGST Ledger Entry (Debit)
        if cgst_amt > 0:
            xml_lines.extend([
                "            <ALLLEDGERENTRIES.LIST>",
                f"              <LEDGERNAME>{escape(self.cgst_ledger)}</LEDGERNAME>",
                "              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
                "              <ISPARTYLEDGER>No</ISPARTYLEDGER>",
                f"              <AMOUNT>-{cgst_amt:.2f}</AMOUNT>",
                "            </ALLLEDGERENTRIES.LIST>",
            ])

        # 4. SGST Ledger Entry (Debit)
        if sgst_amt > 0:
            xml_lines.extend([
                "            <ALLLEDGERENTRIES.LIST>",
                f"              <LEDGERNAME>{escape(self.sgst_ledger)}</LEDGERNAME>",
                "              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
                "              <ISPARTYLEDGER>No</ISPARTYLEDGER>",
                f"              <AMOUNT>-{sgst_amt:.2f}</AMOUNT>",
                "            </ALLLEDGERENTRIES.LIST>",
            ])

        # 5. Round Off Ledger Entry
        if abs(round_off) >= 0.01:
            xml_lines.extend([
                "            <ALLLEDGERENTRIES.LIST>",
                f"              <LEDGERNAME>{escape(self.round_off_ledger)}</LEDGERNAME>",
                f"              <ISDEEMEDPOSITIVE>{'No' if round_off > 0 else 'Yes'}</ISDEEMEDPOSITIVE>",
                "              <ISPARTYLEDGER>No</ISPARTYLEDGER>",
                f"              <AMOUNT>{-round_off:.2f}</AMOUNT>",
                "            </ALLLEDGERENTRIES.LIST>",
            ])

        # 6. Inventory Items Breakdown
        for item in line_items:
            def extract_val(d, k, def_val):
                v = d.get(k)
                if isinstance(v, dict):
                    return v.get("value", def_val)
                return v if v is not None else def_val

            desc = extract_val(item, "description", "Stock Item")
            qty = float(extract_val(item, "quantity", 1.0) or 1.0)
            rate = float(extract_val(item, "unit_price", 0.0) or 0.0)
            line_tot = float(extract_val(item, "line_total", 0.0) or (qty * rate))

            xml_lines.extend([
                "            <ALLINVENTORYENTRIES.LIST>",
                f"              <STOCKITEMNAME>{escape(str(desc))}</STOCKITEMNAME>",
                "              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
                f"              <RATE>{rate:.2f}/nos</RATE>",
                f"              <AMOUNT>-{line_tot:.2f}</AMOUNT>",
                f"              <ACTUALQTY>{qty:g} nos</ACTUALQTY>",
                f"              <BILLEDQTY>{qty:g} nos</BILLEDQTY>",
                "              <ACCOUNTINGALLOCATIONS.LIST>",
                f"                <LEDGERNAME>{escape(self.purchase_ledger)}</LEDGERNAME>",
                "                <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
                f"                <AMOUNT>-{line_tot:.2f}</AMOUNT>",
                "              </ACCOUNTINGALLOCATIONS.LIST>",
                "            </ALLINVENTORYENTRIES.LIST>",
            ])

        xml_lines.extend([
            "          </VOUCHER>",
            "        </TALLYMESSAGE>",
            "      </REQUESTDATA>",
            "    </IMPORTDATA>",
            "  </BODY>",
            "</ENVELOPE>",
        ])

        return "\n".join(xml_lines)

    def _export_ledger_to_tally(self, doc: dict[str, Any]) -> str:
        """Generate Tally Payment / Receipt Vouchers from cash book or khata ledger."""
        ledger_items = doc.get("ledger_items", [])
        fields = doc.get("fields", {})

        def get_field_val(key: str, default=None):
            f = fields.get(key)
            if f is None and key in doc:
                f = doc.get(key)
            if isinstance(f, dict):
                return f.get("value", default)
            return f if f is not None else default

        book_title = get_field_val("book_title") or get_field_val("customer_name") or "Cash Book"

        xml_lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<ENVELOPE>",
            "  <HEADER>",
            "    <TALLYREQUEST>Import Data</TALLYREQUEST>",
            "  </HEADER>",
            "  <BODY>",
            "    <IMPORTDATA>",
            "      <REQUESTDESC>",
            "        <REPORTNAME>Vouchers</REPORTNAME>",
            "        <STATICVARIABLES>",
            "          <SVCURRENTCOMPANY>##SVCURRENTCOMPANY</SVCURRENTCOMPANY>",
            "        </STATICVARIABLES>",
            "      </REQUESTDESC>",
            "      <REQUESTDATA>",
        ]

        voucher_counter = 1
        for item in ledger_items:
            def extract_val(d, k, def_val):
                v = d.get(k)
                if isinstance(v, dict):
                    return v.get("value", def_val)
                return v if v is not None else def_val

            date_str = extract_val(item, "entry_date", None)
            tally_date = format_tally_date(date_str)
            particulars = extract_val(item, "particulars", "General Expense/Receipt")
            voucher_no = extract_val(item, "voucher_no", None) or f"VCH-{voucher_counter:04d}"

            out_val = float(extract_val(item, "cash_out_debit", 0.0) or 0.0)
            in_val = float(extract_val(item, "cash_in_credit", 0.0) or 0.0)

            if out_val <= 0 and in_val <= 0:
                continue

            if out_val > 0:
                # Payment Voucher (Cash Out): Debit Expense, Credit Cash
                vch_type = "Payment"
                debit_ledger = particulars
                credit_ledger = self.cash_ledger
                amt = out_val
            else:
                # Receipt Voucher (Cash In): Debit Cash, Credit Income/Party
                vch_type = "Receipt"
                debit_ledger = self.cash_ledger
                credit_ledger = particulars
                amt = in_val

            xml_lines.extend([
                '        <TALLYMESSAGE xmlns:UDF="TallyUDF">',
                f'          <VOUCHER VCHTYPE="{vch_type}" ACTION="Create">',
                f"            <DATE>{tally_date}</DATE>",
                f"            <VOUCHERTYPENAME>{vch_type}</VOUCHERTYPENAME>",
                f"            <VOUCHERNUMBER>{escape(str(voucher_no))}</VOUCHERNUMBER>",
                f"            <NARRATION>{escape(str(particulars))} (Ledger: {escape(str(book_title))})</NARRATION>",
                "            <ALLLEDGERENTRIES.LIST>",
                f"              <LEDGERNAME>{escape(str(debit_ledger))}</LEDGERNAME>",
                "              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>",
                f"              <AMOUNT>-{amt:.2f}</AMOUNT>",
                "            </ALLLEDGERENTRIES.LIST>",
                "            <ALLLEDGERENTRIES.LIST>",
                f"              <LEDGERNAME>{escape(str(credit_ledger))}</LEDGERNAME>",
                "              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>",
                f"              <AMOUNT>{amt:.2f}</AMOUNT>",
                "            </ALLLEDGERENTRIES.LIST>",
                "          </VOUCHER>",
                "        </TALLYMESSAGE>",
            ])
            voucher_counter += 1

        xml_lines.extend([
            "      </REQUESTDATA>",
            "    </IMPORTDATA>",
            "  </BODY>",
            "</ENVELOPE>",
        ])

        return "\n".join(xml_lines)
