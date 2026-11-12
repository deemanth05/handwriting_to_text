"""Vendor Fingerprint & Spatial Template Memory Cache Package.

Exports:
- compute_phash, hamming_distance, phash_similarity, extract_header_identifiers
- VendorTemplateStore, vendor_template_store
- TemplateFastExtractor, template_fast_extractor
"""

from backend.app.services.templates.fingerprint import (
    compute_phash,
    extract_header_identifiers,
    hamming_distance,
    is_generic_header,
    phash_similarity,
)
from backend.app.services.templates.fast_extractor import (
    TemplateFastExtractor,
    template_fast_extractor,
)
from backend.app.services.templates.store import (
    VendorTemplateStore,
    vendor_template_store,
)

__all__ = [
    "compute_phash",
    "hamming_distance",
    "phash_similarity",
    "extract_header_identifiers",
    "is_generic_header",
    "VendorTemplateStore",
    "vendor_template_store",
    "TemplateFastExtractor",
    "template_fast_extractor",
]
