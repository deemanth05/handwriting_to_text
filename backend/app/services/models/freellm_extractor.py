"""FreeLLMAPI Vision Extractor Implementation.

Connects to the local FreeLLMAPI router (OpenAI-compatible /v1/chat/completions)
using base64 vision payloads, strict JSON formatting, and timeout management.
Inherits from OpenAICompatibleVisionExtractor to leverage CircuitBreaker protections.
"""

from __future__ import annotations

from backend.app.config import settings
from backend.app.services.models.circuit_breaker import CircuitBreaker
from backend.app.services.models.json_utils import clean_json_text, parse_llm_json  # noqa: F401
from backend.app.services.models.openai_compat import OpenAICompatibleVisionExtractor


class FreeLLMVisionExtractor(OpenAICompatibleVisionExtractor):
    """Vision extractor calling FreeLLMAPI's local proxy router with circuit breaker."""

    def __init__(
        self,
        name: str,
        model_id: str,
        base_url: str = settings.FREELLM_BASE_URL,
        api_key: str = settings.FREELLM_API_KEY,
        timeout_seconds: float = settings.FREELLM_TIMEOUT_SECONDS,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        super().__init__(
            name=name,
            model_id=model_id,
            base_url=base_url,
            api_key=api_key or "freellm-default-token",
            timeout_seconds=timeout_seconds,
            circuit_breaker=circuit_breaker or CircuitBreaker(name=f"cb_{name}"),
        )
