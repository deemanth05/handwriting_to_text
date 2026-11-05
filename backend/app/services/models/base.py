"""Base interfaces for multi-model vision and OCR extraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.app.schemas.document import DocumentType


@dataclass
class RawModelOutput:
    """Verbatim extraction output from a single model."""

    model_name: str
    model_identifier: str
    raw_text: str
    parsed_json: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    status: str = "SUCCESS"  # SUCCESS | ERROR | TIMEOUT
    error: str | None = None


class BaseVisionExtractor(ABC):
    """Abstract base class for vision and OCR extractors."""

    def __init__(self, name: str, model_id: str):
        self.name = name
        self.model_id = model_id

    @abstractmethod
    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        """Extract structured data from an image buffer."""
