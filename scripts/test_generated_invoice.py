import json
import time
import urllib.request
from pathlib import Path

img_path = Path("sample_dataset/real_handwritten_invoice.jpg")
with open(img_path, "rb") as f:
    img_bytes = f.read()

boundary = "----WebKitFormBoundaryRealisticTest"
body = bytearray()
body.extend(
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{img_path.name}"\r\nContent-Type: image/jpeg\r\n\r\n'.encode("utf-8")
)
body.extend(img_bytes)
body.extend(
    f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="doc_type"\r\n\r\nINVOICE\r\n--{boundary}--\r\n'.encode("utf-8")
)

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/extract",
    data=bytes(body),
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
)

t0 = time.perf_counter()
try:
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        elapsed = time.perf_counter() - t0
        print("=== Live Extraction Success ===")
        print("Duration:", round(elapsed, 2), "s")
        print("Document ID:", res.get("document_id"))
        print("Status:", res.get("status"))
        print("Overall Confidence:", res.get("overall_confidence"))
        print("Models Participated:", res.get("models_participated"))
        print("Math Valid:", res.get("math_validation", {}).get("is_valid"))
        print("Line Items Extracted:", len(res.get("line_items", [])))
        for i, item in enumerate(res.get("line_items", [])):
            desc = item.get("description", {}).get("value")
            qty = item.get("quantity", {}).get("value")
            rate = item.get("unit_price", {}).get("value")
            total = item.get("line_total", {}).get("value")
            math_ok = item.get("row_math_valid")
            print(f"  Row {i+1}: '{desc}' | Qty: {qty} | Rate: {rate} | Total: {total} | Math OK: {math_ok}")
        print("\nExtracted Header/Footer Fields:")
        for k, v in res.get("fields", {}).items():
            if v.get("value") is not None:
                print(f"  - {k}: {v.get('value')} (confidence: {v.get('confidence')})")
except Exception as e:
    print("Error:", e)
