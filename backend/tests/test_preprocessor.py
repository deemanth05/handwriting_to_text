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


def test_shadow_removal():
    import numpy as np

    # Synthetic image with white paper (240) and a severe cast shadow gradient (falling to 60)
    h, w = 200, 300
    img = np.full((h, w, 3), 240, dtype=np.uint8)
    for x in range(w):
        shadow_factor = 1.0 - (0.6 * (x / w))  # gradient shadow across width
        img[:, x] = np.clip(img[:, x] * shadow_factor, 0, 255).astype(np.uint8)

    # Pre-shadow variance
    pre_std = float(np.std(img[:, :, 0]))
    normalized = preprocessor.remove_shadows_rolling_ball(img, kernel_size=35)
    post_std = float(np.std(normalized[:, :, 0]))

    # Background division must dramatically reduce shadow illumination variation
    assert post_std < pre_std * 0.5


def test_wolf_binarization():
    import numpy as np

    # Synthetic image with faint strokes (gray level 160 on 220 paper)
    gray = np.full((150, 150), 220, dtype=np.uint8)
    gray[70:80, 20:130] = 150  # faint ballpoint stroke

    thresh = preprocessor.wolf_binarization(gray, window_size=25, k=0.35)
    assert thresh.shape == gray.shape
    unique_vals = set(np.unique(thresh))
    assert unique_vals.issubset({0, 255})
    # Foreground stroke must be detected as black (0)
    assert np.mean(thresh[70:80, 20:130] == 0) > 0.80


def test_perspective_dewarp():
    import cv2
    import numpy as np

    # Create a white synthetic canvas with a large dark skewed quadrilateral on a contrasting border
    canvas = np.zeros((600, 800, 3), dtype=np.uint8)
    # Define a trapezoid simulating a phone camera angle
    pts = np.array([[120, 100], [680, 120], [740, 500], [80, 480]], dtype=np.int32)
    cv2.fillPoly(canvas, [pts], (240, 240, 240))
    cv2.polylines(canvas, [pts], isClosed=True, color=(20, 20, 20), thickness=4)

    dewarped, was_warped = preprocessor.perspective_dewarp(canvas)
    assert was_warped is True
    assert dewarped.shape[0] > 0
    assert dewarped.shape[1] > 0


def test_shadow_removal_even_kernel():
    import numpy as np

    img = np.full((100, 100, 3), 200, dtype=np.uint8)
    # Even kernel_size (30) must not crash OpenCV GaussianBlur
    res = preprocessor.remove_shadows_rolling_ball(img, kernel_size=30)
    assert res.shape == img.shape


def test_perspective_dewarp_diamond_quad():
    import cv2
    import numpy as np

    canvas = np.zeros((600, 600, 3), dtype=np.uint8)
    pts = np.array([[300, 80], [520, 300], [300, 520], [80, 300]], dtype=np.int32)
    cv2.fillPoly(canvas, [pts], (240, 240, 240))
    cv2.polylines(canvas, [pts], isClosed=True, color=(20, 20, 20), thickness=4)

    dewarped, was_warped = preprocessor.perspective_dewarp(canvas)
    assert was_warped is True
    assert dewarped.shape[0] > 0
    assert dewarped.shape[1] > 0

