"""Unit tests for Generic OpenAI-Compatible Vision Extractor (LM Studio / vLLM / FreeLLMAPI)."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.schemas.document import DocumentType
from backend.app.services.models.circuit_breaker import CircuitBreaker
from backend.app.services.models.openai_compat import OpenAICompatibleVisionExtractor


@pytest.mark.asyncio
async def test_openai_compat_markdown_json_parsing():
    raw_markdown = """
    ```json
    {
        "vendor": "Apex Supplies",
        "invoice_number": "APX-99",
        "total_amount": 1200.50
    }
    ```
    """
    sample_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": raw_markdown,
                }
            }
        ]
    }

    mock_resp = httpx.Response(
        status_code=200,
        json=sample_response_data,
        request=httpx.Request("POST", "http://127.0.0.1:1234/v1/chat/completions"),
    )

    extractor = OpenAICompatibleVisionExtractor(
        name="test_lmstudio",
        model_id="local-model",
        base_url="http://127.0.0.1:1234/v1",
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await extractor.extract(b"dummy_bytes", DocumentType.INVOICE)

        assert result.status == "SUCCESS"
        assert result.parsed_json["vendor"] == "Apex Supplies"
        assert result.parsed_json["total_amount"] == 1200.50


@pytest.mark.asyncio
async def test_openai_compat_rate_limit_trips_breaker():
    cb = CircuitBreaker(name="test_lmstudio_cb", failure_threshold=3)
    extractor = OpenAICompatibleVisionExtractor(
        name="test_lmstudio",
        model_id="local-model",
        base_url="http://127.0.0.1:1234/v1",
        circuit_breaker=cb,
    )

    mock_429 = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        request=httpx.Request("POST", "http://127.0.0.1:1234/v1/chat/completions"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_429
        result = await extractor.extract(b"dummy_bytes", DocumentType.INVOICE)

        assert result.status == "RATE_LIMITED"
        # Immediate trip on 429
        assert cb.can_execute() is False

        # Next call fails fast via circuit breaker
        result_fast = await extractor.extract(b"dummy_bytes", DocumentType.INVOICE)
        assert result_fast.status == "CIRCUIT_OPEN"
        assert result_fast.latency_ms == 0.0
