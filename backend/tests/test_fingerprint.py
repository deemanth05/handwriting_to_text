"""Tests for DCT-Based Perceptual Hashing & Header Identifier Extraction."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from backend.app.services.templates.fingerprint import (
    compute_phash,
    extract_header_identifiers,
    hamming_distance,
    phash_similarity,
)

SAMPLE_DIR = Path("sample_dataset")


def test_phash_determinism():
    """Identical image input must generate identical 64-bit hash (distance 0)."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    img = cv2.imread(str(img_path))
    assert img is not None, "Failed to load sample_invoice.png"

    h1 = compute_phash(img)
    h2 = compute_phash(img)
    assert h1 == h2
    assert len(h1) == 16
    assert hamming_distance(h1, h2) == 0
    assert phash_similarity(h1, h2) == 1.0


def test_phash_illumination_invariance():
    """pHash must remain highly stable under realistic brightness/contrast shifts (distance <= 4)."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    orig = cv2.imread(str(img_path))
    assert orig is not None

    h_orig = compute_phash(orig)

    # Moderate brightness boost
    bright = cv2.convertScaleAbs(orig, alpha=1.0, beta=25)
    h_bright = compute_phash(bright)
    dist_bright = hamming_distance(h_orig, h_bright)
    assert dist_bright <= 4, f"Brightness shift caused high divergence: {dist_bright}"

    # Moderate contrast boost
    contrast = cv2.convertScaleAbs(orig, alpha=1.2, beta=0)
    h_contrast = compute_phash(contrast)
    dist_contrast = hamming_distance(h_orig, h_contrast)
    assert dist_contrast <= 4, f"Contrast shift caused high divergence: {dist_contrast}"


def test_phash_distinct_layout_divergence():
    """Different documents must yield significant Hamming distance (>= 15 bits)."""
    inv_path = SAMPLE_DIR / "sample_invoice.png"
    ledger_path = SAMPLE_DIR / "sample_petty_cash.webp"
    handwritten_path = SAMPLE_DIR / "real_handwritten_invoice.jpg"

    h_inv = compute_phash(cv2.imread(str(inv_path)))
    h_ledger = compute_phash(cv2.imread(str(ledger_path)))
    h_hw = compute_phash(cv2.imread(str(handwritten_path)))

    assert hamming_distance(h_inv, h_ledger) >= 15
    assert hamming_distance(h_inv, h_hw) >= 15
    assert hamming_distance(h_ledger, h_hw) >= 15


def test_phash_bytes_input():
    """compute_phash should handle raw image bytes transparently."""
    img_path = SAMPLE_DIR / "sample_invoice.png"
    raw_bytes = img_path.read_bytes()

    h_bytes = compute_phash(raw_bytes)
    h_cv = compute_phash(cv2.imread(str(img_path)))
    assert h_bytes == h_cv


def test_extract_header_identifiers_gstin():
    """Verify regex extraction of Indian 15-character GSTIN."""
    sample_ocr = [
        {"text": "TAX INVOICE / CASH MEMO", "y_min": 10, "y_max": 30, "y": 20},
        {"text": "MAHALAXMI HARDWARE & TOOLS", "y_min": 35, "y_max": 65, "y": 50},
        {"text": "Main Road, Pune - 411002", "y_min": 70, "y_max": 90, "y": 80},
        {"text": "GSTIN: 27AABCS1429B1Z1", "y_min": 95, "y_max": 115, "y": 105},
        {"text": "Date: 12/11/2026", "y_min": 120, "y_max": 140, "y": 130},
        {"text": "Invoice No: MH-902", "y_min": 120, "y_max": 140, "y": 130},
    ]

    gstin, vendor_name = extract_header_identifiers(sample_ocr, doc_height=1000)
    assert gstin == "27AABCS1429B1Z1"
    assert vendor_name == "MAHALAXMI HARDWARE & TOOLS"


def test_extract_header_identifiers_without_gstin():
    """Verify graceful handling when GSTIN is missing (unregistered vendor)."""
    sample_ocr = [
        {"text": "Shree Ganesh Petty Store", "y_min": 15, "y_max": 40, "y": 25},
        {"text": "Station Road", "y_min": 45, "y_max": 65, "y": 55},
        {"text": "Cash Memo", "y_min": 70, "y_max": 90, "y": 80},
    ]

    gstin, vendor_name = extract_header_identifiers(sample_ocr, doc_height=800)
    assert gstin is None
    assert vendor_name == "Shree Ganesh Petty Store"


def test_is_generic_header_detection():
    """Verify generic document titles and copy notices are rejected from vendor names."""
    from backend.app.services.templates.fingerprint import is_generic_header

    assert is_generic_header("INVOICE") is True
    assert is_generic_header("TAX INVOICE / CASH MEMO") is True
    assert is_generic_header("DUPLICATE") is True
    assert is_generic_header("Original For Recipient") is True
    assert is_generic_header("Your Logo Here") is True
    assert is_generic_header("Page No 1") is True
    assert is_generic_header("See Rule 138A") is True
    assert is_generic_header("INVOICEBILLFORMAT") is True

    # Real vendors must not be classified as generic
    assert is_generic_header("SHREE GANESH GENERAL STORES") is False
    assert is_generic_header("Quorum Club LLp") is False
    assert is_generic_header("TATA STARBUCKS PRIVATE LIMITED") is False
    assert is_generic_header("Ad4Tech Materials") is False
    assert is_generic_header("Mahalaxmi Hardware") is False


def test_extract_header_identifiers_skips_generic_titles():
    """Verify that candidate vendor extraction skips generic title rows."""
    sample_ocr = [
        {"text": "INVOICE", "y_min": 10, "y_max": 30, "y": 20},
        {"text": "DUPLICATE FOR TRANSPORTER", "y_min": 35, "y_max": 55, "y": 45},
        {"text": "AD4TECH MATERIALS PVT LTD", "y_min": 60, "y_max": 90, "y": 75},
        {"text": "Date: 25.10.2026", "y_min": 95, "y_max": 115, "y": 105},
    ]
    gstin, vendor_name = extract_header_identifiers(sample_ocr, doc_height=1000)
    assert vendor_name == "AD4TECH MATERIALS PVT LTD"


def test_compute_phash_pil_image():
    """Verify compute_phash accepts PIL Image inputs seamlessly."""
    from PIL import Image
    pil_img = Image.open(SAMPLE_DIR / "sample_invoice.png")
    cv_img = cv2.imread(str(SAMPLE_DIR / "sample_invoice.png"))

    h_pil = compute_phash(pil_img)
    h_cv = compute_phash(cv_img)
    assert h_pil == h_cv
