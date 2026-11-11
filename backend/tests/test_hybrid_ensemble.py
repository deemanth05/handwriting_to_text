"""Integration tests for Hybrid Multi-Model Dispatcher with Circuit Breakers."""

import pytest

from backend.app.schemas.document import DocumentType
from backend.app.services.ensemble import EnsembleDispatcher
from backend.app.services.models.mock_extractor import MockVisionExtractor


@pytest.mark.asyncio
async def test_hybrid_ensemble_telemetry_reporting():
    dispatcher = EnsembleDispatcher(
        extractors=[
            MockVisionExtractor("m1", "id1", {"vendor": "Local Mart"}),
        ]
    )
    telemetry = dispatcher.get_circuit_breaker_telemetry()
    assert "freellm" in telemetry
    assert "ollama" in telemetry
    assert "lmstudio" in telemetry
    assert telemetry["freellm"]["state"] == "CLOSED"


@pytest.mark.asyncio
async def test_hybrid_ensemble_fast_failover_when_remote_models_trip(sample_invoice_bytes: bytes):
    # Simulated fleet where remote VLM models fail
    remote_vlm1 = MockVisionExtractor("gemini_vlm", "remote_a", should_fail=True)
    remote_vlm2 = MockVisionExtractor("qwen_vl", "remote_b", should_fail=True)

    dispatcher = EnsembleDispatcher(extractors=[remote_vlm1, remote_vlm2])
    result = await dispatcher.dispatch(sample_invoice_bytes, DocumentType.INVOICE)

    # Local fallbacks (RapidOCR / Surya) guarantee recovery
    assert len(result.successful_runs) >= 1
    assert result.degraded_mode is True
    assert result.confidence_penalty > 0.0
    assert any("rapidocr" in r.model_name or "surya" in r.model_name for r in result.successful_runs)
