"""DCT-Based Perceptual Hashing & Header Identifier Extraction.

Computes 64-bit perceptual hashes (pHash) on document images using OpenCV 2D DCT.
Extracts 15-character Indian GSTIN and candidate vendor legal titles from document headers.
Zero mock data: operates strictly on real image pixels and OCR bounding boxes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Standard Indian 15-character GSTIN regex (State Code (2) + PAN (10) + Entity (1) + 'Z' + Checksum (1))
GSTIN_REGEX = re.compile(
    r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Zz]{1}[0-9A-Z]{1})\b"
)
GSTIN_PREFIXED_REGEX = re.compile(
    r"(?:GSTIN|GST\s*NO|GSTIN/UIN)[:\s.-]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Zz]{1}[0-9A-Z]{1})",
    re.IGNORECASE,
)

# Common header keywords that indicate non-vendor meta information
HEADER_IGNORE_KEYWORDS = [
    "tax invoice",
    "retail invoice",
    "cash memo",
    "bill of supply",
    "invoice no",
    "invoice #",
    "bill no",
    "date",
    "dinank",
    "gstin",
    "gst no",
    "ph:",
    "phone",
    "mobile",
    "tel:",
    "email",
    "pan no",
    "pan:",
    "original for recipient",
    "duplicate for transporter",
    "triplicate for supplier",
    "consignee",
    "buyer",
    "ship to",
    "bill to",
    "s.no",
    "particulars",
    "description",
    "qty",
    "quantity",
    "rate",
    "amount",
    "total",
]

GENERIC_DOCUMENT_TITLES = {
    "invoice",
    "tax invoice",
    "retail invoice",
    "cash memo",
    "bill of supply",
    "bill format",
    "invoice bill format",
    "invoicebillformat",
    "duplicate",
    "original",
    "triplicate",
    "quadruplicate",
    "consignee copy",
    "transporter copy",
    "customer copy",
    "office copy",
    "consignor copy",
    "your logo",
    "your logo here",
    "logo here",
    "company logo",
    "add logo",
    "page no",
    "page number",
    "see rule",
    "see rule 138a",
    "proforma invoice",
    "delivery challan",
    "quotation",
    "estimate",
    "purchase order",
    "cash/credit memo",
    "credit memo",
    "debit memo",
    "original for recipient",
    "duplicate for transporter",
    "triplicate for supplier",
}


def is_generic_header(text: str) -> bool:
    """Determine whether text is a generic document title, copy note, or template placeholder.

    Prevents generic headers like 'INVOICE', 'DUPLICATE', or 'Page No' from poisoning
    the vendor template cache.
    """
    if not text:
        return True
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text).lower().strip()
    norm = " ".join(cleaned.split())
    if not norm or len(norm) < 3:
        return True
    if norm in GENERIC_DOCUMENT_TITLES:
        return True
    if any(norm.startswith(p) for p in ["page no", "see rule", "your logo", "rule 138", "copy of", "original for", "duplicate for", "triplicate for"]):
        return True
    # Strip common noise tokens and check if anything substantial remains
    stripped = re.sub(
        r"\b(tax|invoice|bill|format|memo|cash|credit|page|no|original|duplicate|triplicate|copy|logo|here|your|recipient|transporter|supplier|consignee|consignor)\b",
        "",
        norm,
    ).strip()
    stripped_clean = re.sub(r"\s+", "", stripped)
    if len(stripped_clean) < 3:
        return True
    return False


def compute_phash(img: np.ndarray | bytes | Any) -> str:
    """Compute a 64-bit DCT-based perceptual hash (pHash) for an image.

    Algorithm:
    1. Grayscale conversion.
    2. Resize to 32x32 using area interpolation.
    3. 2D Discrete Cosine Transform (DCT) via cv2.dct.
    4. Extract top-left 8x8 low-frequency matrix (64 coefficients).
    5. Compute median of AC frequencies (excluding DC component at (0,0)).
    6. Generate 64-bit fingerprint: 1 if coefficient > median else 0.
    7. Return 16-character hexadecimal string representation.
    """
    if hasattr(img, "convert") and hasattr(img, "size"):
        # PIL Image support: convert directly to grayscale to match cv2 BGR2GRAY bit-for-bit
        img = np.array(img.convert("L"))

    if isinstance(img, (bytes, bytearray)):
        nparr = np.frombuffer(img, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError("Failed to decode image bytes for pHash computation.")
        image_data = decoded
    elif isinstance(img, np.ndarray):
        image_data = img
    else:
        raise TypeError(f"Unsupported image type for pHash: {type(img)}")

    if image_data.size == 0:
        raise ValueError("Image is empty.")

    # Convert to grayscale
    if len(image_data.shape) == 3:
        if image_data.shape[2] == 4:
            gray = cv2.cvtColor(image_data, cv2.COLOR_BGRA2GRAY)
        elif image_data.shape[2] == 3:
            gray = cv2.cvtColor(image_data, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_data[:, :, 0]
    else:
        gray = image_data

    # 32x32 resize
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)

    # 2D DCT on float32
    dct_matrix = cv2.dct(np.float32(resized))

    # Extract 8x8 low-frequency components
    dct_8x8 = dct_matrix[:8, :8]
    flat = dct_8x8.flatten()

    # Median excluding DC component flat[0]
    ac_median = float(np.median(flat[1:]))

    # Binary hash: 64 bits
    bits = (flat > ac_median).astype(int)

    # Convert 64 bits to integer and format as 16-character hex
    hash_int = 0
    for b in bits:
        hash_int = (hash_int << 1) | int(b)

    return f"{hash_int:016x}"


def hamming_distance(h1: str, h2: str) -> int:
    """Compute bitwise Hamming distance between two 16-character hex hashes (0 to 64)."""
    try:
        val1 = int(h1, 16)
        val2 = int(h2, 16)
        return bin(val1 ^ val2).count("1")
    except Exception as e:
        logger.warning("Failed to compute Hamming distance between '%s' and '%s': %s", h1, h2, e)
        return 64


def phash_similarity(h1: str, h2: str) -> float:
    """Compute normalized visual similarity ratio between 0.0 (opposite) and 1.0 (identical)."""
    dist = hamming_distance(h1, h2)
    return max(0.0, min(1.0, 1.0 - (dist / 64.0)))


def extract_header_identifiers(
    ocr_data: Any,
    doc_height: float | None = None,
) -> tuple[str | None, str | None]:
    """Scan OCR results or boxes for GSTIN and Vendor Business Legal Name.

    Returns:
        (gstin, vendor_name)
    """
    gstin: str | None = None
    vendor_name: str | None = None

    boxes: list[dict[str, Any]] = []

    # Normalize various input formats
    if isinstance(ocr_data, list):
        if len(ocr_data) > 0 and isinstance(ocr_data[0], dict):
            boxes = ocr_data
        elif len(ocr_data) > 0 and isinstance(ocr_data[0], (list, tuple)):
            # RapidOCR format [box, text, score]
            for item in ocr_data:
                if len(item) >= 2:
                    text = str(item[1]).strip()
                    box = item[0]
                    xs = [p[0] for p in box] if isinstance(box, (list, tuple)) else [0, 0]
                    ys = [p[1] for p in box] if isinstance(box, (list, tuple)) else [0, 0]
                    boxes.append({
                        "text": text,
                        "x_min": min(xs),
                        "x_max": max(xs),
                        "y_min": min(ys),
                        "y_max": max(ys),
                        "y": sum(ys) / len(ys) if ys else 0.0,
                    })
        elif len(ocr_data) > 0 and isinstance(ocr_data[0], str):
            # Pure text lines
            for idx, line in enumerate(ocr_data):
                boxes.append({
                    "text": line.strip(),
                    "y_min": idx * 30.0,
                    "y_max": (idx + 1) * 30.0,
                    "y": idx * 30.0 + 15.0,
                })
    elif isinstance(ocr_data, str):
        lines = ocr_data.splitlines()
        for idx, line in enumerate(lines):
            boxes.append({
                "text": line.strip(),
                "y_min": idx * 30.0,
                "y_max": (idx + 1) * 30.0,
                "y": idx * 30.0 + 15.0,
            })

    if not boxes:
        return None, None

    # Sort boxes top to bottom
    sorted_boxes = sorted(boxes, key=lambda b: float(b.get("y_min", b.get("y", 0.0))))

    # 1. Search for GSTIN across all header text
    # In invoices, GSTIN can appear at top right or top left
    full_text = " ".join(b.get("text", "") for b in sorted_boxes[:20])

    m_pref = GSTIN_PREFIXED_REGEX.search(full_text)
    if m_pref:
        gstin = m_pref.group(1).upper()
    else:
        m_raw = GSTIN_REGEX.search(full_text)
        if m_raw:
            gstin = m_raw.group(1).upper()

    # 2. Extract Candidate Vendor Name
    # Filter to top 35% of page if doc_height is known, otherwise top 8 boxes
    header_threshold = (0.35 * doc_height) if doc_height else float("inf")
    candidate_boxes = [
        b for idx, b in enumerate(sorted_boxes[:12])
        if float(b.get("y_min", 0.0)) <= header_threshold
    ]

    for b in candidate_boxes:
        txt = b.get("text", "").strip()
        if len(txt) < 3:
            continue

        lower_txt = txt.lower()

        # Check if line is a generic header or contains ignore keywords
        if is_generic_header(txt) or any(kw in lower_txt for kw in HEADER_IGNORE_KEYWORDS):
            continue

        # Skip GSTIN line if it's the GSTIN itself
        if gstin and gstin.lower() in lower_txt:
            continue

        # Skip lines that are purely numeric, phone numbers, or dates
        digits_count = sum(c.isdigit() for c in txt)
        letters_count = sum(c.isalpha() for c in txt)
        if letters_count < 3 or digits_count > letters_count:
            continue

        # Skip street address indicators if alone
        if any(w in lower_txt for w in ["road,", "street,", "complex,", "post,", "dist.", "pin:", "pincode"]):
            continue

        # Found candidate vendor name!
        # Clean up leading/trailing non-alphanumeric noise
        cleaned = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", txt)
        # Strip unclosed opening parentheses or trailing brackets
        cleaned = re.sub(r"[\(\[\{\)\]\}]+$", "", cleaned).strip()
        if len(cleaned) >= 3 and not is_generic_header(cleaned):
            vendor_name = cleaned
            break

    return gstin, vendor_name
