"""Verification Script for Dynamic Layout and Table Structure Recognition."""

import asyncio
from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.schemas.document import DocumentType
from backend.app.services.models.rapidocr_local import RapidOCRLocalExtractor


async def main():
    ext = RapidOCRLocalExtractor()

    print("=" * 80)
    print("VERIFICATION 1: sample_dataset/real_handwritten_invoice.jpg")
    print("=" * 80)
    p1 = Path("sample_dataset/real_handwritten_invoice.jpg")
    res1 = await ext.extract(p1.read_bytes(), DocumentType.INVOICE)
    assert res1.status == "SUCCESS"
    pj1 = res1.parsed_json
    items1 = pj1.get("line_items", [])
    print(f"Line items count: {len(items1)}")
    assert len(items1) == 7, f"Expected exactly 7 line items, got {len(items1)}"
    for i, it in enumerate(items1):
        print(f"  {i+1}: {it['description']} | Qty: {it['quantity']} | Rate: {it['unit_price']} | LineTotal: {it['line_total']}")
    print("Subtotal:", pj1.get("subtotal"))
    print("Tax Amount:", pj1.get("tax_amount"))
    print("Grand Total:", pj1.get("grand_total"))
    assert pj1.get("subtotal") == 7580.0
    assert pj1.get("tax_amount") == 1364.4
    assert pj1.get("grand_total") == 8990.0

    print("\n" + "=" * 80)
    print("VERIFICATION 2: sample_dataset/sample_petty_cash.webp")
    print("=" * 80)
    p2 = Path("sample_dataset/sample_petty_cash.webp")
    res2 = await ext.extract(p2.read_bytes(), DocumentType.CASH_BOOK)
    assert res2.status == "SUCCESS"
    pj2 = res2.parsed_json
    items2 = pj2.get("ledger_items", [])
    print(f"Ledger items count: {len(items2)}")
    assert len(items2) == 12, f"Expected 12 items, got {len(items2)}"
    assert "opening" in items2[0]["particulars"].lower()
    assert items2[0]["running_balance"] == 200.0 or items2[0]["cash_in_credit"] == 200.0
    print("First item:", items2[0])
    print("Last item:", items2[-1])

    print("\n" + "=" * 80)
    print("VERIFICATION 3: sample_dataset/sample_invoice.png")
    print("=" * 80)
    p3 = Path("sample_dataset/sample_invoice.png")
    res3 = await ext.extract(p3.read_bytes(), DocumentType.INVOICE)
    assert res3.status == "SUCCESS"
    pj3 = res3.parsed_json
    items3 = pj3.get("line_items", [])
    print(f"Line items count: {len(items3)}")
    assert len(items3) == 4
    print("Vendor:", pj3.get("vendor_name"))
    print("Subtotal:", pj3.get("subtotal"))

    print("\n" + "=" * 80)
    print("ALL REAL-WORLD VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
