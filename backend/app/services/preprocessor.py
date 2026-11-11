"""Image Pre-Processing Service using OpenCV, NumPy and Pillow.

Performs:
1. Security validation (magic bytes, size check, decompression bomb protection)
2. 4-point quadrilateral perspective dewarp to rectify mobile phone camera angle
3. Hough baseline rotation deskewing as secondary fine-tilt correction
4. Rolling-ball background division for glare and dark phone shadow removal
5. CLAHE illumination normalization on LAB color space
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

    def perspective_dewarp(self, cv_bgr: np.ndarray) -> tuple[np.ndarray, bool]:
        """Detect document quadrilateral boundary and rectify mobile camera perspective tilt."""
        gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return cv_bgr, False

        h, w = cv_bgr.shape[:2]
        img_area = float(h * w)
        min_area = img_area * 0.20
        max_area = img_area * 0.98

        best_quad = None
        max_found_area = 0.0

        sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
        for c in sorted_contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                area = float(cv2.contourArea(approx))
                if min_area <= area <= max_area and area > max_found_area:
                    max_found_area = area
                    best_quad = approx.reshape(4, 2)

        if best_quad is None:
            return cv_bgr, False

        # Order points robustly: top-left, top-right, bottom-right, bottom-left
        pts = best_quad.astype(np.float32)
        cx, cy = np.mean(pts, axis=0)
        angles = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
        sort_idx = np.argsort(angles)
        pts_sorted = pts[sort_idx]

        # Anchor top-left at minimum (x + y)
        sums = pts_sorted[:, 0] + pts_sorted[:, 1]
        tl_idx = int(np.argmin(sums))
        rect = np.roll(pts_sorted, -tl_idx, axis=0)

        (tl, tr, br, bl) = rect

        # If points are already at the image frame borders, the image is already cropped
        border_pts = 0
        for pt in [tl, tr, br, bl]:
            if (pt[0] < 0.05 * w or pt[0] > 0.95 * w) and (pt[1] < 0.05 * h or pt[1] > 0.95 * h):
                border_pts += 1
        if border_pts >= 3:
            return cv_bgr, False

        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_w = max(int(width_a), int(width_b))

        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_h = max(int(height_a), int(height_b))

        if max_w < 100 or max_h < 100:
            return cv_bgr, False

        dst = np.array(
            [
                [0, 0],
                [max_w - 1, 0],
                [max_w - 1, max_h - 1],
                [0, max_h - 1],
            ],
            dtype=np.float32,
        )

        matrix = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(
            cv_bgr, matrix, (max_w, max_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return warped, True

    def deskew(self, cv_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        """Detect and correct slight rotation tilts (-45° to +45°)."""
        gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 200, apertureSize=3)

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
                    if -45.0 <= theta <= 45.0:
                        angles.append(theta)

            if angles:
                angle = float(np.median(angles))

        if abs(angle) > 0.5:
            (h, w) = cv_bgr.shape[:2]
            center = (w // 2, h // 2)
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            deskewed = cv2.warpAffine(
                cv_bgr, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            return deskewed, angle

        return cv_bgr, 0.0

    def remove_shadows_rolling_ball(self, cv_bgr: np.ndarray, kernel_size: int = 35) -> np.ndarray:
        """Morphological background division to eliminate mobile phone cast shadows and glare."""
        ksize = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
        ksize = max(3, ksize)
        lab = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        bg = cv2.morphologyEx(l_chan, cv2.MORPH_DILATE, kernel)
        bg = cv2.GaussianBlur(bg, (ksize, ksize), 0)

        # Division normalization
        norm_l = np.clip(
            (l_chan.astype(np.float32) / (bg.astype(np.float32) + 1e-5)) * 255.0, 0, 255
        ).astype(np.uint8)

        merged = cv2.merge((norm_l, a_chan, b_chan))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    def apply_clahe(self, cv_bgr: np.ndarray) -> np.ndarray:
        """Apply CLAHE on LAB color space to equalize illumination and contrast."""
        lab = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl_chan = clahe.apply(l_chan)

        merged_lab = cv2.merge((cl_chan, a_chan, b_chan))
        enhanced_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)
        return enhanced_bgr

    def process(self, raw_bytes: bytes) -> PreprocessedBundle:
        """Run the complete 4-stage image enhancement pipeline."""
        self.validate_security(raw_bytes)

        nparr = np.frombuffer(raw_bytes, np.uint8)
        cv_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if cv_bgr is None:
            raise ImageSecurityError("Failed to decode image buffer.")

        # 1. 4-point quadrilateral perspective dewarp
        warped_bgr, was_warped = self.perspective_dewarp(cv_bgr)
        if was_warped:
            oriented_bgr = warped_bgr
            angle = 0.0
        else:
            oriented_bgr, angle = self.deskew(cv_bgr)

        # 2. Rolling-ball morphological background division for shadow removal
        shadow_removed_bgr = self.remove_shadows_rolling_ball(oriented_bgr)

        # 3. CLAHE illumination normalization
        enhanced_bgr = self.apply_clahe(shadow_removed_bgr)

        # Encode back to JPEG bytes
        _, enhanced_buf = cv2.imencode(".jpg", enhanced_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

        (h, w) = enhanced_bgr.shape[:2]

        return PreprocessedBundle(
            original_bytes=raw_bytes,
            enhanced_rgb_bytes=enhanced_buf.tobytes(),
            deskew_angle=angle,
            width=w,
            height=h,
        )


preprocessor = ImagePreprocessor()
