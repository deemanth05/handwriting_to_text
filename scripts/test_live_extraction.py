"""Test live API extraction with real image payload."""

import json
import urllib.request
from pathlib import Path

img_path = Path("sample_dataset/sample_invoice.png")
if not img_path.exists():
    img_path = Path("sample_dataset/sample_khata.png")

with open(img_path, "rb") as f:
    img_bytes = f.read()

boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body = bytearray()
body.extend(
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{img_path.name}"\r\nContent-Type: image/png\r\n\r\n'.encode("utf-8")
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

print(f"Sending extraction request to http://127.0.0.1:8000/api/v1/extract with {img_path.name}...")
try:
    with urllib.request.urlopen(req, timeout=45.0) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("\n=== Live Extraction Succeeded ===")
        print("Document ID:", res.get("document_id"))
        print("Status:", res.get("status"))
        print("Overall Confidence:", res.get("overall_confidence"))
        print("Models Participated:", res.get("models_participated"))
        print("Math Valid:", res.get("math_validation", {}).get("is_valid"))
        print("Line Items Extracted:", len(res.get("line_items", [])))
        print("Sample Fields Extracted:")
        for k, v in list(res.get("fields", {}).items())[:5]:
            print(f"  - {k}: {v.get('value')} (conf: {v.get('confidence')})")
except Exception as e:
    print("Extraction Request Error:", e)
