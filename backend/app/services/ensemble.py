"""Asynchronous Multi-Model Vision & OCR Dispatcher with Hybrid Model Routing.

Executes uncorrelated vision/OCR extraction pipelines concurrently using asyncio.gather().
Supports:
- Cloud/Proxy Vision Models (FreeLLMAPI)
- Local Air-Gapped Multimodal VLMs (Ollama native /api/chat with grammar JSON mode)
- Local OpenAI-compatible inference servers (LM Studio / vLLM / LocalAI)
- Local Transformer OCR (Surya Multilingual OCR)
- Local Lightweight ONNX OCR (RapidOCR)

Features enterprise CircuitBreaker protection:
- Instant fail-fast (0ms) when an upstream runtime is rate-limited (HTTP 429) or down
- Dynamic degraded mode calculation and penalty scoring
- Zero-trust fallback to dual local engines (RapidOCR + Surya)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput
from backend.app.services.models.circuit_breaker import CircuitBreaker
from backend.app.services.models.freellm_extractor import FreeLLMVisionExtractor
from backend.app.services.models.mock_extractor import MockVisionExtractor
from backend.app.services.models.ollama_extractor import OllamaVisionExtractor
from backend.app.services.models.openai_compat import OpenAICompatibleVisionExtractor
from backend.app.services.models.rapidocr_local import RapidOCRLocalExtractor
from backend.app.services.models.surya_local import SuryaLocalExtractor


@dataclass
class EnsembleDispatchResult:
    """Consolidated outcome of the multi-model parallel execution."""

    successful_runs: list[RawModelOutput] = field(default_factory=list)
    failed_runs: list[RawModelOutput] = field(default_factory=list)
    total_duration_ms: float = 0.0
    confidence_penalty: float = 0.0
    degraded_mode: bool = False
    runtime_telemetry: dict[str, Any] = field(default_factory=dict)


class EnsembleDispatcher:
    """Dispatches multiple vision extractors in parallel with automatic circuit breakers."""

    def __init__(self, extractors: list[BaseVisionExtractor] | None = None):
        self._custom_extractors = extractors is not None

        # Shared provider circuit breakers
        self.circuit_breakers: dict[str, CircuitBreaker] = {
            "freellm": CircuitBreaker(
                name="freellm",
                failure_threshold=getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 2),
                recovery_timeout_seconds=getattr(settings, "CIRCUIT_BREAKER_RECOVERY_SECONDS", 30.0),
            ),
            "ollama": CircuitBreaker(
                name="ollama",
                failure_threshold=getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 2),
                recovery_timeout_seconds=getattr(settings, "CIRCUIT_BREAKER_RECOVERY_SECONDS", 30.0),
            ),
            "lmstudio": CircuitBreaker(
                name="lmstudio",
                failure_threshold=getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 2),
                recovery_timeout_seconds=getattr(settings, "CIRCUIT_BREAKER_RECOVERY_SECONDS", 30.0),
            ),
        }

        # Local deterministic fallbacks
        self.local_fallback = RapidOCRLocalExtractor(
            name="rapidocr_local",
            model_id="rapidocr-onnx",
        )
        self.surya_fallback = SuryaLocalExtractor(
            name="surya_local",
            model_id="surya-ocr",
            langs=getattr(settings, "SURYA_LANGS", ["en", "hi"]),
        )

        if extractors:
            self.extractors = extractors
        elif settings.USE_MOCK_FALLBACK:
            self.extractors = [
                MockVisionExtractor(name="gemini_vlm", model_id="mock_model_a"),
                MockVisionExtractor(name="qwen_vl", model_id="mock_model_b"),
                MockVisionExtractor(name="rapidocr_local", model_id="mock_model_c"),
            ]
        else:
            self.extractors = self._build_default_extractor_fleet()

    def _build_default_extractor_fleet(self) -> list[BaseVisionExtractor]:
        """Construct the hybrid fleet consisting of cloud/proxy, local VLMs, and local OCR."""
        fleet: list[BaseVisionExtractor] = []

        # 1. Cloud / Local Proxy Vision Models (FreeLLMAPI)
        fleet.append(
            FreeLLMVisionExtractor(
                name="gemini_vlm",
                model_id=settings.FREELLM_MODEL_A,
                circuit_breaker=self.circuit_breakers["freellm"],
            )
        )
        fleet.append(
            FreeLLMVisionExtractor(
                name="qwen_vl",
                model_id=settings.FREELLM_MODEL_B,
                circuit_breaker=self.circuit_breakers["freellm"],
            )
        )

        # 2. Local Air-Gapped Multimodal VLM via Ollama (e.g. gemma3:12b, minicpm-v, qwen2.5-vl)
        if getattr(settings, "ENABLE_OLLAMA", True):
            fleet.append(
                OllamaVisionExtractor(
                    name="ollama_vision",
                    model_id=getattr(settings, "OLLAMA_MODEL", "gemma3:12b"),
                    base_url=getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                    timeout_seconds=getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 30.0),
                    circuit_breaker=self.circuit_breakers["ollama"],
                )
            )

        # 3. Local OpenAI-Compatible Server (LM Studio / vLLM)
        if getattr(settings, "ENABLE_LMSTUDIO", True):
            fleet.append(
                OpenAICompatibleVisionExtractor(
                    name="lmstudio_vision",
                    model_id=getattr(settings, "LMSTUDIO_MODEL", "local-model"),
                    base_url=getattr(settings, "LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
                    timeout_seconds=getattr(settings, "LMSTUDIO_TIMEOUT_SECONDS", 30.0),
                    circuit_breaker=self.circuit_breakers["lmstudio"],
                )
            )

        # 4. Local Deterministic RapidOCR ONNX
        fleet.append(self.local_fallback)

        # 5. Local Multilingual Transformer Surya OCR
        if getattr(settings, "ENABLE_SURYA_LOCAL", True):
            fleet.append(self.surya_fallback)

        return fleet

    def get_circuit_breaker_telemetry(self) -> dict[str, Any]:
        """Return diagnostic metrics for all active circuit breakers."""
        return {name: cb.get_status() for name, cb in self.circuit_breakers.items()}

    async def _safe_extract(
        self,
        extractor: BaseVisionExtractor,
        image_bytes: bytes,
        doc_type: DocumentType,
    ) -> RawModelOutput:
        """Call extractor with timeout guard and error interception."""
        # Generous timeout guard slightly higher than model timeout
        guard_timeout = getattr(extractor, "timeout", settings.FREELLM_TIMEOUT_SECONDS) + 2.0
        try:
            return await asyncio.wait_for(
                extractor.extract(image_bytes, doc_type),
                timeout=guard_timeout,
            )
        except TimeoutError:
            return RawModelOutput(
                model_name=extractor.name,
                model_identifier=extractor.model_id,
                raw_text="",
                latency_ms=guard_timeout * 1000,
                status="TIMEOUT",
                error=f"Dispatcher timeout after {guard_timeout}s",
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
        """Execute vision models concurrently with circuit-breaker protection."""
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

        # Circuit Breaker: If all models failed (rate limit, offline, timeout),
        # guarantee at least one successful execution via local fallback engines.
        if not successful:
            for fallback_engine in [self.local_fallback, self.surya_fallback]:
                already_succeeded = any(r.model_name == fallback_engine.name for r in successful)
                if not already_succeeded:
                    fallback_res = await self._safe_extract(fallback_engine, image_bytes, doc_type)
                    if fallback_res.status == "SUCCESS" and fallback_res.parsed_json is not None:
                        successful.append(fallback_res)
                        break
                    else:
                        failed.append(fallback_res)

        # Graceful degradation logic:
        # If all or most external models failed, apply graduated confidence penalty
        penalty = 0.0
        degraded = False

        if len(failed) == 1:
            penalty = settings.CONFIDENCE_FAILED_MODEL_PENALTY
            degraded = True
        elif len(failed) == 2:
            penalty = 0.30
            degraded = True
        elif len(failed) >= 3:
            penalty = 0.50 if len(successful) >= 2 else 0.80
            degraded = True

        return EnsembleDispatchResult(
            successful_runs=successful,
            failed_runs=failed,
            total_duration_ms=total_duration,
            confidence_penalty=penalty,
            degraded_mode=degraded,
            runtime_telemetry=self.get_circuit_breaker_telemetry(),
        )


ensemble_dispatcher = EnsembleDispatcher()
