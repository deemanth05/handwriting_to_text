"""OpenAI-Compatible Vision Extractor Implementation.

Supports any standard OpenAI-compatible vision/multimodal endpoint:
- LM Studio (default: http://127.0.0.1:1234/v1)
- FreeLLMAPI (default: http://127.0.0.1:3001/v1)
- vLLM / LocalAI / Ollama v1 endpoints
- Enterprise on-prem GPU cluster inference servers

Features:
- Integrated CircuitBreaker to fail-fast on 429 rate limits or connection outages
- Structured JSON output parsing with markdown codeblock stripping
- Strict latency measurement and error reporting
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput
from backend.app.services.models.circuit_breaker import CircuitBreaker
from backend.app.services.models.json_utils import parse_llm_json
from backend.app.services.models.prompts import get_prompt_for_doctype


class OpenAICompatibleVisionExtractor(BaseVisionExtractor):
    """Vision extractor communicating with OpenAI-compatible multimodal endpoints."""

    def __init__(
        self,
        name: str,
        model_id: str,
        base_url: str,
        api_key: str = "local-token",
        timeout_seconds: float = 15.0,
        circuit_breaker: CircuitBreaker | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(name=name, model_id=model_id)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "local-token"
        self.timeout = timeout_seconds
        self.circuit_breaker = circuit_breaker or CircuitBreaker(name=f"cb_{name}")
        self.extra_headers = extra_headers or {}

    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        """Send multimodal request to OpenAI-compatible endpoint and parse structured JSON."""
        # Circuit Breaker check: fail fast if upstream is rate-limited or offline
        if not self.circuit_breaker.can_execute():
            status_info = self.circuit_breaker.get_status()
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=0.0,
                status="CIRCUIT_OPEN",
                error=(
                    f"Circuit breaker is OPEN for {self.name} "
                    f"({status_info.get('remaining_cooldown_seconds')}s cooldown remaining). "
                    f"Last error: {status_info.get('last_error')}"
                ),
            )

        start_time = time.perf_counter()
        prompt = get_prompt_for_doctype(doc_type)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64_image}"

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "EnterpriseVisionEngine/1.0",
            **self.extra_headers,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                is_rate_limit = response.status_code == 429
                err_msg = f"HTTP {response.status_code}: {response.text[:300]}"
                self.circuit_breaker.record_failure(err_msg, is_rate_limit=is_rate_limit)
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text="",
                    latency_ms=latency_ms,
                    status="RATE_LIMITED" if is_rate_limit else "ERROR",
                    error=err_msg,
                )

            res_data = response.json()
            choices = res_data.get("choices", [])
            if not choices:
                err_msg = "Response returned HTTP 200 but contained no choices."
                self.circuit_breaker.record_failure(err_msg)
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=response.text,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=err_msg,
                )

            raw_content = choices[0].get("message", {}).get("content", "")
            try:
                parsed = parse_llm_json(raw_content)
                self.circuit_breaker.record_success()
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=raw_content,
                    parsed_json=parsed,
                    latency_ms=latency_ms,
                    status="SUCCESS",
                )
            except Exception as pe:
                # Valid HTTP response but malformed JSON; doesn't trip circuit breaker but flags error
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=raw_content,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=f"JSON parsing error: {pe}",
                )

        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Request timed out after {self.timeout}s"
            self.circuit_breaker.record_failure(err_msg)
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=latency_ms,
                status="TIMEOUT",
                error=err_msg,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            err_msg = str(e)
            self.circuit_breaker.record_failure(err_msg)
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=latency_ms,
                status="ERROR",
                error=err_msg,
            )
