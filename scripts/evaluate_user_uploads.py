"""Evaluate and benchmark the 10 real-world user-uploaded invoices and receipts.

Sends each file to the live FastAPI backend at http://127.0.0.1:8000/api/v1/extract
and computes field extraction accuracy, row math verification, and performance matrices.
"""

import json
from pathlib import Path
import httpx
import time

UPLOADS_DIR = Path(r"C:\Users\deema\.gemini\antigravity\brain\2b153fce-3872-419a-b323-4a97a1aaf857\.user_uploaded")
API_URL = "http://127.0.0.1:8000/api/v1/extract"

DOCUMENTS = [
    {
        "id": "DOC-01",
        "file": "media_1794244985703_3268abed.jpg",
        "name": "Ad4tech Material LLC (Printed Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "Ad4tech Material LLC",
        "expected_total": 1564.00,
        "expected_items": 3,
    },
    {
        "id": "DOC-02",
        "file": "media_1794244994171_8c301ab5.jpg",
        "name": "East Repair Inc. (Printed Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "East Repair Inc",
        "expected_total": 154.06,
        "expected_items": 3,
    },
    {
        "id": "DOC-03",
        "file": "media_1794245006288_6e6ac99b.jpg",
        "name": "Invoice Bill Format (Handwritten Notes/Template)",
        "doc_type": "INVOICE",
        "expected_vendor": "CSR",
        "expected_total": None,
        "expected_items": 0,
    },
    {
        "id": "DOC-04",
        "file": "media_1794245016460_61e23b9f.jpg",
        "name": "ABC Corporation (Printed Digital Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "ABC Corporation",
        "expected_total": 2000.00,
        "expected_items": 2,
    },
    {
        "id": "DOC-05",
        "file": "media_1794245032214_2b50d6bf.jpg",
        "name": "ABC Seller / XYZ Buyer (Tax Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "ABC Seller",
        "expected_total": 48557.00,
        "expected_items": 6,
    },
    {
        "id": "DOC-06",
        "file": "media_1794245084506_026bb723.jpg",
        "name": "Hillside Joinery Ltd (Handwritten Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "HILLSIDE JOINERY LTD",
        "expected_total": 406.80,
        "expected_items": 3,
    },
    {
        "id": "DOC-07",
        "file": "media_1794245100323_ba13dad0.jpg",
        "name": "Bharat Associates (Handwritten Tax Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "BHARAT ASSOCIATES",
        "expected_total": 32345.00,
        "expected_items": 3,
    },
    {
        "id": "DOC-08",
        "file": "media_1794245106975_db5d45a0.jpg",
        "name": "The Coffee House (Receipt with Handwritten Note)",
        "doc_type": "INVOICE",
        "expected_vendor": "THE COFFEE HOUSE",
        "expected_total": 42.17,
        "expected_items": 6,
    },
    {
        "id": "DOC-09",
        "file": "media_1794245123052_7b424da9.jpg",
        "name": "New Lite Lumber (Handwritten Construction Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "NEW LITE LUMBER",
        "expected_total": 5895.00,
        "expected_items": 11,
    },
    {
        "id": "DOC-10",
        "file": "media_1794245132036_0c0d0fe5.jpg",
        "name": "Nath Traders (Handwritten Retail Invoice)",
        "doc_type": "INVOICE",
        "expected_vendor": "NATH TRADERS",
        "expected_total": 3186.00,
        "expected_items": 1,
    },
]


def run_benchmark():
    print("=" * 80)
    print("  EVALUATING 10 REAL-WORLD USER-UPLOADED INVOICES & HANDWRITTEN DOCUMENTS")
    print("=" * 80)

    results = []
    total_docs = len(DOCUMENTS)
    successful_http = 0
    math_valid_count = 0
    items_extracted_total = 0

    with httpx.Client(timeout=30.0) as client:
        for idx, doc in enumerate(DOCUMENTS, 1):
            file_path = UPLOADS_DIR / doc["file"]
            if not file_path.exists():
                print(f"[{idx}/{total_docs}] ERROR: File not found: {file_path}")
                continue

            with open(file_path, "rb") as f:
                file_bytes = f.read()

            t0 = time.perf_counter()
            try:
                response = client.post(
                    API_URL,
                    files={"file": (doc["file"], file_bytes, "image/jpeg")},
                    data={"doc_type": doc["doc_type"]},
                )
                duration_ms = (time.perf_counter() - t0) * 1000
                status_code = response.status_code
                resp_json = response.json() if status_code == 200 else {}
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000
                status_code = 500
                resp_json = {"error": str(e)}

            is_http_ok = status_code == 200
            if is_http_ok:
                successful_http += 1

            math_valid = resp_json.get("math_validation", {}).get("is_valid", False)
            if math_valid:
                math_valid_count += 1

            line_items = resp_json.get("line_items", [])
            items_extracted_total += len(line_items)

            fields = resp_json.get("fields", {})
            vendor_extracted = fields.get("vendor_name", {}).get("value")
            total_extracted = fields.get("grand_total", {}).get("value")
            models = resp_json.get("models_participated", [])
            overall_conf = resp_json.get("overall_confidence", 0.0)

            res_record = {
                "id": doc["id"],
                "name": doc["name"],
                "file": doc["file"],
                "status_code": status_code,
                "duration_ms": duration_ms,
                "models": models,
                "items_count": len(line_items),
                "math_valid": math_valid,
                "overall_conf": overall_conf,
                "vendor_extracted": vendor_extracted,
                "total_extracted": total_extracted,
                "line_items": line_items,
                "raw_response": resp_json,
            }
            results.append(res_record)

            status_str = "SUCCESS" if is_http_ok else f"FAIL({status_code})"
            math_str = "VALID MATH" if math_valid else "MATH FLAG"
            print(f"[{idx:02d}/{total_docs:02d}] {doc['name'][:40]:<40} | HTTP {status_code} | {duration_ms:6.1f}ms | Models: {models} | Items: {len(line_items)} | {math_str} | Conf: {overall_conf:.2f}")

    print("\n" + "=" * 80)
    print("  DETAILED EXTRACTION BREAKDOWN PER DOCUMENT")
    print("=" * 80)

    for r in results:
        print(f"\n--- [{r['id']}] {r['name']} ---")
        print(f"  Latency: {r['duration_ms']:.1f}ms | Models: {r['models']} | Confidence: {r['overall_conf']:.2f}")
        print(f"  Vendor Extracted: {r['vendor_extracted']}")
        print(f"  Grand Total Extracted: {r['total_extracted']}")
        print(f"  Math Validated: {r['math_valid']}")
        print(f"  Line Items Extracted ({r['items_count']}):")
        for it in r["line_items"][:5]:
            desc = it.get("description", {}).get("value", "")
            q = it.get("quantity", {}).get("value", 0)
            p = it.get("unit_price", {}).get("value", 0)
            t = it.get("line_total", {}).get("value", 0)
            mv = it.get("row_math_valid", False)
            print(f"    - {desc:<35} | Qty: {q} | Price: {p} | Total: {t} | Math Valid: {mv}")
        if r["items_count"] > 5:
            print(f"    ... and {r['items_count'] - 5} more items")

    print("\n" + "=" * 80)
    print("  PERFORMANCE METRICS MATRIX")
    print("=" * 80)
    print(f"  Total Test Documents:       {total_docs}")
    print(f"  HTTP 200 Extraction Success: {successful_http}/{total_docs} ({successful_http/total_docs*100:.1f}%)")
    print(f"  Math Consistency Rate:      {math_valid_count}/{total_docs} ({math_valid_count/total_docs*100:.1f}%)")
    print(f"  Total Line Items Extracted: {items_extracted_total}")
    avg_latency = sum(r["duration_ms"] for r in results) / len(results) if results else 0
    print(f"  Average Processing Latency: {avg_latency:.1f}ms")
    print("=" * 80)

    # Save results to JSON file
    out_path = Path("sample_dataset/user_uploads_evaluation_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved benchmark results to {out_path.as_posix()}")

if __name__ == "__main__":
    run_benchmark()
