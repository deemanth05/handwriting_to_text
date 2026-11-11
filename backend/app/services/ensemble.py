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
from backend.app.services.models.mock_extractor import MockVisionExtractor
from backend.app.services.models.rapidocr_local import RapidOCRLocalExtractor


@dataclass
class EnsembleDispatchResult:
    """Consolidated outcome of the multi-model parallel execution."""

    successful_runs: list[RawModelOutput] = field(default_factory=list)
    failed_runs: list[RawModelOutput] = field(default_factory=list)
    total_duration_ms: float = 0.0
    confidence_penalty: float = 0.0
    degraded_mode: bool = False


class EnsembleDispatcher:
    """Dispatches multiple vision extractors in parallel with automatic circuit breakers."""

    def __init__(self, extractors: list[BaseVisionExtractor] | None = None):
        self._custom_extractors = extractors is not None
        if extractors:
            self.extractors = extractors
        elif settings.USE_MOCK_FALLBACK:
            self.extractors = [
                MockVisionExtractor(name="gemini_vlm", model_id="mock_model_a"),
                MockVisionExtractor(name="qwen_vl", model_id="mock_model_b"),
                MockVisionExtractor(name="rapidocr_local", model_id="mock_model_c"),
            ]
        else:
            model_a = FreeLLMVisionExtractor(
                name="gemini_vlm",
                model_id=settings.FREELLM_MODEL_A,
            )

            model_b = FreeLLMVisionExtractor(
                name="qwen_vl",
                model_id=settings.FREELLM_MODEL_B,
            )

            # Model C: Local RapidOCR running on CPU with zero network latency (<200ms)
            model_c = RapidOCRLocalExtractor(
                name="rapidocr_local",
                model_id="rapidocr-onnx",
            )

            self.extractors = [model_a, model_b, model_c]

        self.local_fallback = RapidOCRLocalExtractor(
            name="rapidocr_local",
            model_id="rapidocr-onnx",
        )

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
            if res.status == "SUCCESS" and res.parsed_json is not None:
                successful.append(res)
            else:
                failed.append(res)

        # Circuit Breaker: If all vision models failed (rate limit, timeout, offline),
        # automatically invoke the local RapidOCR engine to guarantee >= 1 successful output.
        if not successful:
            already_run = any(r.model_name == self.local_fallback.name for r in successful + failed)
            if not already_run:
                fallback_res = await self._safe_extract(self.local_fallback, image_bytes, doc_type)
                if fallback_res.status == "SUCCESS" and fallback_res.parsed_json is not None:
                    successful.append(fallback_res)
                else:
                    failed.append(fallback_res)

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
        elif len(failed) >= 3:
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
