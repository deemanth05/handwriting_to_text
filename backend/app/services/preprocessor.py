"""Image Pre-Processing Service using OpenCV and Pillow.

Performs:
1. Security validation (magic bytes, size check, decompression bomb protection)
2. Auto-orientation and perspective deskewing
3. Shadow removal and illumination normalization (CLAHE on LAB color space)
4. Adaptive Gaussian thresholding buffer for faint ink / stamp extraction
"""

import io
import math
from dataclasses import dataclass

import cv2
import filetype
import numpy as np
from PIL import Image

from backend.app.config import settings

# Enforce decompression bomb protection
Image.MAX_IMAGE_PIXELS = 50_000_000

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImageSecurityError(ValueError):
    """Raised when an uploaded file fails security checks."""


@dataclass
class PreprocessedBundle:
    """Encapsulates image outputs for downstream extractors."""

    original_bytes: bytes
    enhanced_rgb_bytes: bytes
    threshold_bytes: bytes
    deskew_angle: float
    width: int
    height: int


class ImagePreprocessor:
    """Preprocesses raw photos/scans for multi-model consensus extraction."""

    def __init__(self, max_size_mb: int = settings.MAX_IMAGE_SIZE_MB):
        self.max_bytes = max_size_mb * 1024 * 1024

    def validate_security(self, raw_bytes: bytes) -> str:
        """Validate file size, magic bytes, and dimensions."""
        if not raw_bytes:
            raise ImageSecurityError("Image file buffer is empty.")

        if len(raw_bytes) > self.max_bytes:
            raise ImageSecurityError(
                f"Image size ({len(raw_bytes) / (1024 * 1024):.2f} MB) exceeds maximum allowed limit ({settings.MAX_IMAGE_SIZE_MB} MB)."
            )

        kind = filetype.guess(raw_bytes)
        if kind is None or kind.mime not in ALLOWED_MIME_TYPES:
            detected_mime = kind.mime if kind else "unknown"
            raise ImageSecurityError(
                f"Unsupported or unsafe file type: {detected_mime}. Allowed: JPEG, PNG, WEBP."
            )

        # Check for image decompression safety with PIL
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.verify()
        except Exception as e:
            raise ImageSecurityError(f"Corrupted or malicious image structure: {e}")

        return kind.mime

    def deskew(self, cv_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        """Detect and correct slight rotation tilts (-45° to +45°)."""
        gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        # Invert colors: text will be white on black background
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 200, apertureSize=3)

        # Use Hough transform to detect dominant text baseline angles
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=20)
        angle = 0.0

        if lines is not None and len(lines) > 0:
            angles = []
            for line in lines:
                coords = line.flatten()
                if len(coords) >= 4:
                    x1, y1, x2, y2 = coords[:4]
                    delta_y = float(y2 - y1)
                    delta_x = float(x2 - x1)
                    theta = math.degrees(math.atan2(delta_y, delta_x))
                    # Only consider near-horizontal lines representing text lines
                    if -45.0 <= theta <= 45.0:
                        angles.append(theta)

            if angles:
                angle = float(np.median(angles))

        # Rotate if necessary
        if abs(angle) > 0.5:
            (h, w) = cv_bgr.shape[:2]
            center = (w // 2, h // 2)
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            deskewed = cv2.warpAffine(
                cv_bgr, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            return deskewed, angle

        return cv_bgr, 0.0

    def apply_clahe(self, cv_bgr: np.ndarray) -> np.ndarray:
        """Apply CLAHE on LAB color space to equalize illumination and remove shadows."""
        lab = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl_chan = clahe.apply(l_chan)

        merged_lab = cv2.merge((cl_chan, a_chan, b_chan))
        enhanced_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)
        return enhanced_bgr

    def generate_threshold(self, cv_bgr: np.ndarray) -> np.ndarray:
        """Adaptive Gaussian thresholding for faint ink and stamp marks."""
        gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
        )
        return thresh

    def process(self, raw_bytes: bytes) -> PreprocessedBundle:
        """Run the complete preprocessing pipeline."""
        self.validate_security(raw_bytes)

        # Decode image using OpenCV
        nparr = np.frombuffer(raw_bytes, np.uint8)
        cv_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if cv_bgr is None:
            raise ImageSecurityError("Failed to decode image buffer.")

        # 1. Deskew
        deskewed_bgr, angle = self.deskew(cv_bgr)

        # 2. Illumination correction via CLAHE
        enhanced_bgr = self.apply_clahe(deskewed_bgr)

        # 3. Adaptive threshold buffer
        thresh = self.generate_threshold(enhanced_bgr)

        # Encode back to JPEG/PNG bytes
        _, enhanced_buf = cv2.imencode(".jpg", enhanced_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        _, thresh_buf = cv2.imencode(".png", thresh)

        (h, w) = enhanced_bgr.shape[:2]

        return PreprocessedBundle(
            original_bytes=raw_bytes,
            enhanced_rgb_bytes=enhanced_buf.tobytes(),
            threshold_bytes=thresh_buf.tobytes(),
            deskew_angle=angle,
            width=w,
            height=h,
        )


preprocessor = ImagePreprocessor()
