"""Comprehensive Test Suite for Live Hybrid Multi-Model Extraction Pipeline.

Executes real extraction against all sample document types (Invoice, Khata, Petty Cash, Prescription)
and generates a diagnostic evaluation matrix covering latency, models participated, fields extracted,
and deterministic arithmetic checks.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "http://127.0.0.1:8000/api/v1"

TEST_CASES = [
    {
        "name": "Printed Commercial Invoice",
        "file": "sample_dataset/sample_invoice.png",
        "doc_type": "INVOICE",
    },
    {
        "name": "Handwritten Indian Khata Ledger",
        "file": "sample_dataset/sample_khata.png",
        "doc_type": "KHATA_LEDGER",
    },
    {
        "name": "Petty Cash Book (Devanagari / English)",
        "file": "sample_dataset/sample_petty_cash.webp",
        "doc_type": "CASH_BOOK",
    },
    {
        "name": "Doctor Medical Prescription",
        "file": "sample_dataset/sample_prescription.png",
        "doc_type": "PRESCRIPTION",
    },
]


def post_multipart(url: str, file_path: Path, doc_type: str, timeout: float = 60.0) -> dict[str, Any]:
    boundary = "----WebKitFormBoundary" + hex(int(time.time() * 1000))[2:]
    content_type = "image/webp" if file_path.suffix == ".webp" else "image/png"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body = bytearray()
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_path.name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8")
    )
    body.extend(file_bytes)
    body.extend(
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="doc_type"\r\n\r\n{doc_type}\r\n--{boundary}--\r\n'.encode("utf-8")
    )

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_tests():
    print("=" * 80)
    print("   ENTERPRISE MULTI-MODEL CONSENSUS ENGINE: LIVE END-TO-END PIPELINE TEST")
    print("=" * 80)

    # 1. Probe Active Runtimes
    print("\n[Step 1] Probing Active Model Runtimes...")
    try:
        req = urllib.request.Request(f"{BASE_URL}/health/runtimes")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            runtimes = health.get("runtimes", {})
            for r_name, r_info in runtimes.items():
                status = r_info.get("status")
                extra = ""
                if r_info.get("models"):
                    extra = f" | Models: {r_info['models']}"
                elif r_info.get("engine"):
                    extra = f" | Engine: {r_info['engine']}"
                print(f"  • {r_name.upper():<16}: [{status}] {extra}")
    except Exception as e:
        print(f"  [-] Failed to reach health endpoint: {e}")
        return

    # 2. Execute Documents
    print("\n[Step 2] Executing Document Extractions across Real Document Portfolio...\n")
    results_summary = []

    for tc in TEST_CASES:
        p = Path(tc["file"])
        if not p.exists():
            print(f"  [-] Missing file: {tc['file']}")
            continue

        print(f"  --> Testing: {tc['name']} ({p.name}) | Type: {tc['doc_type']}")
        t0 = time.perf_counter()
        try:
            res = post_multipart(f"{BASE_URL}/extract", p, tc["doc_type"])
            elapsed_sec = time.perf_counter() - t0

            doc_id = res.get("document_id", "unknown")
            status = res.get("status")
            confidence = res.get("overall_confidence", 0.0)
            models = res.get("models_participated", [])
            math_valid = res.get("math_validation", {}).get("is_valid", False)
            line_items_count = len(res.get("line_items", []))
            ledger_items_count = len(res.get("ledger_items", []))
            fields = res.get("fields", {})

            print(f"      Status: {status} | Conf: {confidence:.2f} | Math Valid: {math_valid} | Elapsed: {elapsed_sec:.2f}s")
            print(f"      Models Participated: {models}")
            if line_items_count > 0:
                print(f"      Line Items Extracted: {line_items_count}")
            if ledger_items_count > 0:
                print(f"      Ledger Items Extracted: {ledger_items_count}")

            extracted_sample = {k: v.get("value") for k, v in list(fields.items())[:3] if v.get("value")}
            if extracted_sample:
                print(f"      Sample Extracted Fields: {extracted_sample}")

            results_summary.append({
                "name": tc["name"],
                "file": p.name,
                "doc_type": tc["doc_type"],
                "status": status,
                "confidence": confidence,
                "math_valid": math_valid,
                "models": models,
                "items": line_items_count or ledger_items_count,
                "latency_sec": round(elapsed_sec, 2),
            })
            print("      [+] OK\n")

        except Exception as e:
            elapsed_sec = time.perf_counter() - t0
            print(f"      [-] ERROR ({elapsed_sec:.2f}s): {e}\n")
            results_summary.append({
                "name": tc["name"],
                "file": p.name,
                "doc_type": tc["doc_type"],
                "status": "ERROR",
                "confidence": 0.0,
                "math_valid": False,
                "models": [],
                "items": 0,
                "latency_sec": round(elapsed_sec, 2),
            })

    # 3. Print Results Summary Table
    print("=" * 80)
    print("                      PORTFOLIO TEST RESULTS MATRIX")
    print("=" * 80)
    print(f"{'Document Name':<32} {'Type':<14} {'Status':<13} {'Conf':<6} {'Math':<6} {'Latency':<8}")
    print("-" * 80)
    for r in results_summary:
        print(
            f"{r['name'][:30]:<32} "
            f"{r['doc_type']:<14} "
            f"{r['status']:<13} "
            f"{r['confidence']:<6.2f} "
            f"{'PASS' if r['math_valid'] else 'REVIEW':<6} "
            f"{r['latency_sec']}s"
        )
    print("=" * 80)


if __name__ == "__main__":
    run_tests()
