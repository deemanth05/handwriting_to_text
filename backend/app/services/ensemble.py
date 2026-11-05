"""Asynchronous Multi-Model Vision Dispatcher.

Executes 3 uncorrelated vision/OCR extraction pipelines concurrently using asyncio.gather().
Handles independent timeouts, errors, and enforces graceful degradation.
"""

import asyncio
import time
from dataclasses import dataclass, field

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput
from backend.app.services.models.freellm_extractor import FreeLLMVisionExtractor
from backend.app.services.models.hybrid_ocr import HybridOCRExtractor
from backend.app.services.models.mock_extractor import MockVisionExtractor


@dataclass
class EnsembleDispatchResult:
    """Consolidated outcome of the 3-model parallel execution."""

    successful_runs: list[RawModelOutput] = field(default_factory=list)
    failed_runs: list[RawModelOutput] = field(default_factory=list)
    total_duration_ms: float = 0.0
    confidence_penalty: float = 0.0
    degraded_mode: bool = False


class EnsembleDispatcher:
    """Dispatches multiple vision extractors in parallel."""

    def __init__(self, extractors: list[BaseVisionExtractor] | None = None):
        if extractors:
            self.extractors = extractors
        elif settings.USE_MOCK_FALLBACK:
            self.extractors = [
                MockVisionExtractor(name="gemini_vlm", model_id="mock_model_a"),
                MockVisionExtractor(name="qwen_vl", model_id="mock_model_b"),
                MockVisionExtractor(name="hybrid_ocr", model_id="mock_model_c"),
            ]
        else:
            self.extractors = [
                FreeLLMVisionExtractor(
                    name="gemini_vlm",
                    model_id=settings.FREELLM_MODEL_A,
                ),
                FreeLLMVisionExtractor(
                    name="qwen_vl",
                    model_id=settings.FREELLM_MODEL_B,
                ),
                HybridOCRExtractor(
                    name="hybrid_ocr",
                    model_id=settings.FREELLM_MODEL_C_STRUCT,
                ),
            ]

    async def _safe_extract(
        self,
        extractor: BaseVisionExtractor,
        image_bytes: bytes,
        doc_type: DocumentType,
    ) -> RawModelOutput:
        """Call extractor with timeout guard."""
        try:
            return await asyncio.wait_for(
                extractor.extract(image_bytes, doc_type),
                timeout=settings.FREELLM_TIMEOUT_SECONDS + 2.0,
            )
        except TimeoutError:
            return RawModelOutput(
                model_name=extractor.name,
                model_identifier=extractor.model_id,
                raw_text="",
                latency_ms=(settings.FREELLM_TIMEOUT_SECONDS + 2.0) * 1000,
                status="TIMEOUT",
                error=f"Dispatcher timeout after {settings.FREELLM_TIMEOUT_SECONDS + 2.0}s",
            )
        except Exception as e:
            return RawModelOutput(
                model_name=extractor.name,
                model_identifier=extractor.model_id,
                raw_text="",
                status="ERROR",
                error=str(e),
            )

    async def dispatch(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> EnsembleDispatchResult:
        """Execute all vision models concurrently."""
        start_time = time.perf_counter()

        tasks = [self._safe_extract(ext, image_bytes, doc_type) for ext in self.extractors]

        results = await asyncio.gather(*tasks, return_exceptions=False)
        total_duration = (time.perf_counter() - start_time) * 1000

        successful: list[RawModelOutput] = []
        failed: list[RawModelOutput] = []

        for res in results:
            if res.status == "SUCCESS" and res.parsed_json:
                successful.append(res)
            else:
                failed.append(res)

        # Graceful degradation logic:
        # If 1 of 3 failed: penalty = -0.10
        # If 2 of 3 failed: penalty = -0.30
        penalty = 0.0
        degraded = False

        if len(failed) == 1:
            penalty = settings.CONFIDENCE_FAILED_MODEL_PENALTY
            degraded = True
        elif len(failed) == 2:
            penalty = 0.30
            degraded = True
        elif len(failed) == 3:
            penalty = 0.80
            degraded = True

        return EnsembleDispatchResult(
            successful_runs=successful,
            failed_runs=failed,
            total_duration_ms=total_duration,
            confidence_penalty=penalty,
            degraded_mode=degraded,
        )


ensemble_dispatcher = EnsembleDispatcher()
