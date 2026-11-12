"""Unit Tests for Multi-Page Container Rasterization Service."""

import io
import zipfile
import pytest
from PIL import Image
import pypdfium2 as pdfium

from backend.app.services.multipage.rasterizer import (
    DocumentRasterizer,
    RasterizationError,
    natural_sort_key,
)


def _create_sample_image(text: str, width: int = 200, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()


def _create_synthetic_pdf(page_count: int = 2) -> bytes:
    pdf = pdfium.PdfDocument.new()
    for _ in range(page_count):
        pdf.new_page(width=595, height=842)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_natural_sort_key():
    filenames = ["page_10.jpg", "page_1.jpg", "page_2.jpg", "page_20.jpg"]
    sorted_files = sorted(filenames, key=natural_sort_key)
    assert sorted_files == ["page_1.jpg", "page_2.jpg", "page_10.jpg", "page_20.jpg"]


def test_single_image_passthrough():
    img_bytes = _create_sample_image("Single Page", 300, 150)
    rasterizer = DocumentRasterizer()

    buffers = rasterizer.rasterize(img_bytes, filename="invoice.jpg")
    assert len(buffers) == 1
    assert buffers[0].page_number == 1
    assert buffers[0].width == 300
    assert buffers[0].height == 150
    assert buffers[0].mime_type == "image/jpeg"


def test_pdf_rasterization():
    pdf_bytes = _create_synthetic_pdf(page_count=3)
    rasterizer = DocumentRasterizer(rasterize_scale=1.0)

    buffers = rasterizer.rasterize(pdf_bytes, filename="bill.pdf")
    assert len(buffers) == 3
    for idx, b in enumerate(buffers, 1):
        assert b.page_number == idx
        assert b.mime_type == "image/jpeg"
        assert b.width == 595
        assert b.height == 842
        assert len(b.raw_bytes) > 0


def test_pdf_exceeds_max_pages():
    pdf_bytes = _create_synthetic_pdf(page_count=5)
    rasterizer = DocumentRasterizer(max_pages=3)

    with pytest.raises(RasterizationError, match="exceeds maximum page limit"):
        rasterizer.rasterize(pdf_bytes)


def test_zip_bundle_extraction_and_natural_order():
    p1 = _create_sample_image("Page 1", 100, 100)
    p2 = _create_sample_image("Page 2", 100, 100)
    p10 = _create_sample_image("Page 10", 100, 100)

    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, mode="w") as zf:
        # Add out of order
        zf.writestr("scans/page_10.jpg", p10)
        zf.writestr("scans/page_1.jpg", p1)
        zf.writestr("scans/page_2.jpg", p2)
        zf.writestr("scans/readme.txt", b"Ignore non-image files")

    zip_bytes = zip_io.getvalue()
    rasterizer = DocumentRasterizer()
    buffers = rasterizer.rasterize(zip_bytes, filename="stapled_bill.zip")

    assert len(buffers) == 3
    # Check natural order: page_1 -> page_2 -> page_10
    assert buffers[0].page_number == 1
    assert "page_1.jpg" in buffers[0].source_filename

    assert buffers[1].page_number == 2
    assert "page_2.jpg" in buffers[1].source_filename

    assert buffers[2].page_number == 3
    assert "page_10.jpg" in buffers[2].source_filename


def test_empty_buffer_fails():
    rasterizer = DocumentRasterizer()
    with pytest.raises(RasterizationError, match="empty"):
        rasterizer.rasterize(b"")


def test_unsupported_format_fails():
    rasterizer = DocumentRasterizer()
    with pytest.raises(RasterizationError, match="Unsupported file format"):
        rasterizer.rasterize(b"This is just random raw text bytes", filename="notes.txt")


def test_corrupt_pdf_fails():
    rasterizer = DocumentRasterizer()
    corrupt_pdf = b"%PDF-1.4\nthis is clearly corrupt binary garbage %%EOF"
    with pytest.raises(RasterizationError, match="Corrupt or invalid PDF"):
        rasterizer.rasterize(corrupt_pdf, filename="bad.pdf")


def test_corrupt_zip_fails():
    rasterizer = DocumentRasterizer()
    corrupt_zip = b"PK\x03\x04\x00\x00not a valid zip structure"
    with pytest.raises(RasterizationError, match="Corrupt or invalid ZIP"):
        rasterizer.rasterize(corrupt_zip, filename="bad.zip")


def test_zip_directory_traversal_filtering():
    p1 = _create_sample_image("P1")
    p2 = _create_sample_image("P2")
    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, mode="w") as zf:
        zf.writestr("../evil.jpg", p1)
        zf.writestr("/root_leak.jpg", p1)
        zf.writestr("page_1.jpg", p1)
        zf.writestr("page_2.jpg", p2)

    rasterizer = DocumentRasterizer()
    buffers = rasterizer.rasterize(zip_io.getvalue(), filename="safe.zip")
    assert len(buffers) == 2
    assert buffers[0].page_number == 1
    assert buffers[0].source_filename == "page_1.jpg"
    assert buffers[1].page_number == 2
    assert buffers[1].source_filename == "page_2.jpg"
