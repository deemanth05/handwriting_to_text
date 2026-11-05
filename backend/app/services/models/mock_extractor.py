"""Mock Extractor for Offline Testing and CI/CD.

Allows deterministic validation of reconciler, consensus calibration,
Hungarian bipartite matching, and graceful degradation without network access.
"""

from typing import Any

from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput


class MockVisionExtractor(BaseVisionExtractor):
    """Deterministic extractor for testing."""

    def __init__(
        self,
        name: str,
        model_id: str,
        preset_json: dict[str, Any] | None = None,
        should_fail: bool = False,
        should_timeout: bool = False,
        latency_ms: float = 120.0,
    ):
        super().__init__(name=name, model_id=model_id)
        self.preset_json = preset_json or {}
        self.should_fail = should_fail
        self.should_timeout = should_timeout
        self.latency_ms = latency_ms

    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        if self.should_timeout:
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=self.latency_ms,
                status="TIMEOUT",
                error="Mock timeout simulated.",
            )

        if self.should_fail:
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=self.latency_ms,
                status="ERROR",
                error="Mock failure simulated.",
            )

        return RawModelOutput(
            model_name=self.name,
            model_identifier=self.model_id,
            raw_text=str(self.preset_json),
            parsed_json=self.preset_json,
            latency_ms=self.latency_ms,
            status="SUCCESS",
        )
