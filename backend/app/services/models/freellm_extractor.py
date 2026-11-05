"""FreeLLMAPI Vision Extractor Implementation.

Connects to the local FreeLLMAPI router (OpenAI-compatible /v1/chat/completions)
using base64 vision payloads, strict JSON formatting, and timeout management.
"""

import base64
import json
import re
import time

import httpx

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput
from backend.app.services.models.prompts import get_prompt_for_doctype


def clean_json_text(text: str) -> str:
    """Strip markdown code fence blocks (```json ... ```) or conversational fluff."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # If starting with { and ending with }, return as is
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()
    return text


class FreeLLMVisionExtractor(BaseVisionExtractor):
    """Vision extractor calling FreeLLMAPI's local proxy router."""

    def __init__(
        self,
        name: str,
        model_id: str,
        base_url: str = settings.FREELLM_BASE_URL,
        api_key: str = settings.FREELLM_API_KEY,
        timeout_seconds: float = settings.FREELLM_TIMEOUT_SECONDS,
    ):
        super().__init__(name=name, model_id=model_id)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "freellm-default-token"
        self.timeout = timeout_seconds

    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        """Send multimodal request to FreeLLMAPI and parse output."""
        start_time = time.perf_counter()
        prompt = get_prompt_for_doctype(doc_type)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64_image}"

        payload = {
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
            "User-Agent": "PaperExtractionEngine/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                err_msg = f"FreeLLMAPI returned HTTP {response.status_code}: {response.text}"
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text="",
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=err_msg,
                )

            res_data = response.json()
            choices = res_data.get("choices", [])
            if not choices:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=response.text,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error="FreeLLMAPI returned response without choices.",
                )

            raw_content = choices[0].get("message", {}).get("content", "")
            cleaned = clean_json_text(raw_content)

            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as jde:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=raw_content,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=f"JSON parsing error: {jde}",
                )

            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text=raw_content,
                parsed_json=parsed,
                latency_ms=latency_ms,
                status="SUCCESS",
            )

        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=latency_ms,
                status="TIMEOUT",
                error=f"Request timed out after {self.timeout}s",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=latency_ms,
                status="ERROR",
                error=str(e),
            )
