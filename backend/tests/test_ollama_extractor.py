"""Unit tests for Native Ollama Vision Extractor."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.schemas.document import DocumentType
from backend.app.services.models.circuit_breaker import CircuitBreaker
from backend.app.services.models.ollama_extractor import OllamaVisionExtractor


@pytest.mark.asyncio
async def test_ollama_extractor_success():
    sample_response_data = {
        "model": "gemma3:12b",
        "message": {
            "role": "assistant",
            "content": json.dumps({
                "vendor": "SuperMart",
                "invoice_number": "INV-101",
                "total_amount": 250.00,
                "line_items": [
                    {"description": "Item 1", "quantity": 1, "unit_price": 250.00, "total": 250.00}
                ],
            }),
        },
    }

    mock_resp = httpx.Response(
        status_code=200,
        json=sample_response_data,
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )

    extractor = OllamaVisionExtractor(
        name="test_ollama",
        model_id="gemma3:12b",
        base_url="http://127.0.0.1:11434",
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await extractor.extract(b"dummy_image_bytes", DocumentType.INVOICE)

        assert result.status == "SUCCESS"
        assert result.model_name == "test_ollama"
        assert result.parsed_json["vendor"] == "SuperMart"
        assert result.parsed_json["total_amount"] == 250.00

        # Verify payload contains format: json and raw image bytes
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["format"] == "json"
        assert payload["model"] == "gemma3:12b"
        assert len(payload["messages"][0]["images"]) == 1


@pytest.mark.asyncio
async def test_ollama_extractor_circuit_breaker_fail_fast():
    cb = CircuitBreaker(name="test_cb", failure_threshold=1)
    cb.record_failure("offline")

    extractor = OllamaVisionExtractor(
        name="test_ollama",
        model_id="gemma3:12b",
        circuit_breaker=cb,
    )

    # When circuit breaker is OPEN, extract fails fast without network call
    result = await extractor.extract(b"dummy_image_bytes", DocumentType.INVOICE)
    assert result.status == "CIRCUIT_OPEN"
    assert result.latency_ms == 0.0
    assert "Circuit breaker is OPEN" in (result.error or "")


@pytest.mark.asyncio
async def test_ollama_extractor_timeout_handling():
    extractor = OllamaVisionExtractor(
        name="test_ollama",
        model_id="gemma3:12b",
        timeout_seconds=0.1,
    )

    with patch.object(httpx.AsyncClient, "post", side_effect=httpx.TimeoutException("Read timed out")):
        result = await extractor.extract(b"dummy_image_bytes", DocumentType.INVOICE)
        assert result.status == "TIMEOUT"
        assert "timed out" in (result.error or "").lower()
