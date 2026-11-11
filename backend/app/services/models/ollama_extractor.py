"""Native Ollama Vision Extractor Implementation.

Connects to Ollama's native multimodal chat API (`/api/chat`) using:
- Grammar-constrained sampling via `"format": "json"` to guarantee valid JSON syntax
- Raw base64 image encoding in `messages[].images`
- CircuitBreaker protection for offline or overloaded local instances
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


class OllamaVisionExtractor(BaseVisionExtractor):
    """Vision extractor communicating with a local or remote Ollama server."""

    def __init__(
        self,
        name: str = "ollama_vision",
        model_id: str = "gemma3:12b",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 30.0,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        super().__init__(name=name, model_id=model_id)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.circuit_breaker = circuit_breaker or CircuitBreaker(name=f"cb_{name}")

    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        """Send multimodal request to Ollama native /api/chat endpoint."""
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

        # Ollama expects raw base64 string without 'data:image/jpeg;base64,' prefix
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
            },
        }

        endpoint = f"{self.base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                is_rate_limit = response.status_code == 429
                err_msg = f"Ollama HTTP {response.status_code}: {response.text[:300]}"
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
            raw_content = res_data.get("message", {}).get("content", "")
            if not raw_content:
                err_msg = "Ollama returned response without content in message."
                self.circuit_breaker.record_failure(err_msg)
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=response.text,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=err_msg,
                )

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
            err_msg = f"Ollama request timed out after {self.timeout}s"
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
