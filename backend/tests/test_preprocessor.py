"""Tests for OpenCV/PIL Preprocessing and Security Validation."""

import io

import pytest
from PIL import Image

from backend.app.services.preprocessor import ImageSecurityError, preprocessor


def test_validate_security_empty_buffer():
    with pytest.raises(ImageSecurityError, match="empty"):
        preprocessor.validate_security(b"")


def test_validate_security_invalid_mime():
    with pytest.raises(ImageSecurityError, match="Unsupported or unsafe"):
        preprocessor.validate_security(b"<html><head><script>alert(1)</script></head></html>")


def test_validate_security_size_limit():
    # Simulate oversized buffer (> 10MB)
    oversized = b"A" * (11 * 1024 * 1024)
    with pytest.raises(ImageSecurityError, match="exceeds maximum"):
        preprocessor.validate_security(oversized)


def test_process_valid_image(sample_invoice_bytes: bytes):
    bundle = preprocessor.process(sample_invoice_bytes)
    assert bundle.original_bytes == sample_invoice_bytes
    assert len(bundle.enhanced_rgb_bytes) > 0
    assert len(bundle.threshold_bytes) > 0
    assert bundle.width > 0
    assert bundle.height > 0
    assert isinstance(bundle.deskew_angle, float)


def test_deskew_rotation():
    # Create intentionally rotated image with text/lines
    from PIL import ImageDraw

    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.line((50, 150, 350, 150), fill=(0, 0, 0), width=5)
    draw.text((60, 130), "Testing line deskew", fill=(0, 0, 0))
    rotated = img.rotate(5)
    buf = io.BytesIO()
    rotated.save(buf, format="PNG")
    raw_rotated = buf.getvalue()

    bundle = preprocessor.process(raw_rotated)
    assert bundle.width > 0
