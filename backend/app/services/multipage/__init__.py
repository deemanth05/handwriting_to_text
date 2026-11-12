"""Multi-Page Document Processing Package.

Provides:
- DocumentRasterizer: Container ingestion for multi-page PDFs, ZIP archives, and single images.
- MultiPageStitcher: Cross-page table continuation stitching and ledger continuity validation.
"""

from backend.app.services.multipage.rasterizer import (
    DocumentRasterizer,
    PageBuffer,
    RasterizationError,
)
from backend.app.services.multipage.stitcher import (
    MultiPageStitcher,
)

__all__ = [
    "DocumentRasterizer",
    "PageBuffer",
    "RasterizationError",
    "MultiPageStitcher",
]
