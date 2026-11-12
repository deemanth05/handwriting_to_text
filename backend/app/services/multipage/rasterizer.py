"""Document Container Ingestion & Rasterization Service.

Provides secure parsing, rasterization, and extraction for:
1. Multi-Page PDFs (via Google PDFium through pypdfium2)
2. Stapled Document ZIP Bundles (with natural numerical ordering and zip-bomb security)
3. Single Image Pass-Through (JPEG, PNG, WEBP)
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any

import filetype
from PIL import Image
import pypdfium2 as pdfium

from backend.app.config import settings

# Enforce decompression bomb limits
Image.MAX_IMAGE_PIXELS = 50_000_000

MAX_PAGES_LIMIT = 25
MAX_ZIP_EXTRACTED_BYTES = 100 * 1024 * 1024  # 100 MB max uncompressed


class RasterizationError(ValueError):
    """Raised when container ingestion or page rasterization fails."""


@dataclass
class PageBuffer:
    """Represents a single rasterized or extracted page ready for OCR/vision."""

    page_number: int  # 1-indexed
    raw_bytes: bytes  # Normalized JPEG/PNG bytes
    mime_type: str
    width: int
    height: int
    source_filename: str = ""


def natural_sort_key(s: str) -> list[Any]:
    """Natural sort key to sort 'page_1', 'page_2', 'page_10' correctly."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


class DocumentRasterizer:
    """Ingests multi-page PDFs, stapled ZIP archives, or single images and produces ordered PageBuffers."""

    def __init__(
        self,
        max_pages: int = MAX_PAGES_LIMIT,
        rasterize_scale: float = 2.0,  # ~144 DPI for crisp text extraction
    ):
        self.max_pages = max_pages
        self.rasterize_scale = rasterize_scale

    def detect_container_type(self, raw_bytes: bytes) -> str:
        """Identify MIME type from magic bytes."""
        if not raw_bytes:
            raise RasterizationError("Input file buffer is empty.")

        # Check PDF header directly
        if raw_bytes.startswith(b"%PDF-"):
            return "application/pdf"

        # Check ZIP header directly (PK\x03\x04)
        if raw_bytes.startswith(b"PK\x03\x04"):
            return "application/zip"

        kind = filetype.guess(raw_bytes)
        if kind is not None:
            return kind.mime

        return "application/octet-stream"

    def rasterize(self, raw_bytes: bytes, filename: str = "document") -> list[PageBuffer]:
        """Dispatches container unpacking based on detected file type."""
        container_type = self.detect_container_type(raw_bytes)

        if container_type == "application/pdf":
            return self._rasterize_pdf(raw_bytes, filename)
        elif container_type == "application/zip":
            return self._extract_zip(raw_bytes, filename)
        elif container_type in {"image/jpeg", "image/png", "image/webp"}:
            return self._single_image_passthrough(raw_bytes, container_type, filename)
        else:
            raise RasterizationError(
                f"Unsupported or unsafe file format (Unsupported file format: '{container_type}'). Supported: PDF, ZIP (stapled images), JPEG, PNG, WEBP."
            )

    def _rasterize_pdf(self, pdf_bytes: bytes, filename: str) -> list[PageBuffer]:
        """Rasterize each PDF page into high-resolution JPEG bytes using pypdfium2."""
        try:
            pdf = pdfium.PdfDocument(pdf_bytes)
        except Exception as e:
            raise RasterizationError(f"Corrupt or invalid PDF file: {e!s}")

        page_count = len(pdf)
        if page_count == 0:
            raise RasterizationError("PDF contains zero pages.")

        if page_count > self.max_pages:
            raise RasterizationError(
                f"PDF exceeds maximum page limit ({page_count} pages > {self.max_pages} limit)."
            )

        buffers: list[PageBuffer] = []
        for idx in range(page_count):
            page_num = idx + 1
            try:
                page = pdf[idx]
                pil_image = page.render(scale=self.rasterize_scale).to_pil()

                # Ensure RGB mode (handles CMYK or grayscale PDFs)
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")

                out_io = io.BytesIO()
                pil_image.save(out_io, format="JPEG", quality=92)
                jpeg_bytes = out_io.getvalue()

                buffers.append(
                    PageBuffer(
                        page_number=page_num,
                        raw_bytes=jpeg_bytes,
                        mime_type="image/jpeg",
                        width=pil_image.width,
                        height=pil_image.height,
                        source_filename=f"{filename}_page_{page_num}.jpg",
                    )
                )
            except Exception as e:
                raise RasterizationError(f"Failed to rasterize PDF page {page_num}: {e!s}")

        return buffers

    def _extract_zip(self, zip_bytes: bytes, filename: str) -> list[PageBuffer]:
        """Safely extract and naturally sort image pages from a stapled ZIP archive."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except Exception as e:
            raise RasterizationError(f"Corrupt or invalid ZIP archive: {e!s}")

        valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
        image_entries = [
            info for info in zf.infolist()
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX")
            and ".." not in info.filename
            and not info.filename.startswith("/")
            and any(info.filename.lower().endswith(ext) for ext in valid_exts)
        ]

        if not image_entries:
            raise RasterizationError("ZIP archive contains no supported image files (.jpg, .png, .webp).")

        if len(image_entries) > self.max_pages:
            raise RasterizationError(
                f"ZIP contains {len(image_entries)} pages, exceeding limit of {self.max_pages}."
            )

        # Zip bomb protection: enforce total uncompressed size limit
        total_uncompressed = sum(info.file_size for info in image_entries)
        if total_uncompressed > MAX_ZIP_EXTRACTED_BYTES:
            raise RasterizationError(
                f"ZIP uncompressed payload ({total_uncompressed / (1024*1024):.1f} MB) exceeds safety threshold."
            )

        # Sort entries using natural numerical sort on filename
        image_entries.sort(key=lambda info: natural_sort_key(info.filename))

        buffers: list[PageBuffer] = []
        for idx, info in enumerate(image_entries, 1):
            img_bytes = zf.read(info)
            try:
                with Image.open(io.BytesIO(img_bytes)) as pil_img:
                    w, h = pil_img.size
                    mime = Image.MIME.get(pil_img.format, "image/jpeg")
            except Exception as e:
                raise RasterizationError(f"Invalid image in ZIP '{info.filename}': {e!s}")

            buffers.append(
                PageBuffer(
                    page_number=idx,
                    raw_bytes=img_bytes,
                    mime_type=mime,
                    width=w,
                    height=h,
                    source_filename=info.filename,
                )
            )

        if not buffers:
            raise RasterizationError("No valid image pages could be extracted from ZIP archive.")

        return buffers

    def _single_image_passthrough(
        self, raw_bytes: bytes, mime_type: str, filename: str
    ) -> list[PageBuffer]:
        """Direct pass-through for single images with dimensional extraction."""
        try:
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                w, h = pil_img.size
        except Exception as e:
            raise RasterizationError(f"Corrupt or invalid image: {e!s}")

        return [
            PageBuffer(
                page_number=1,
                raw_bytes=raw_bytes,
                mime_type=mime_type,
                width=w,
                height=h,
                source_filename=filename,
            )
        ]
