"""Direct Google Gemini Vision API Extractor.

Calls Google AI Studio directly (gemini-2.5-flash / gemini-1.5-flash) via official REST API,
bypassing unreliable intermediate proxies. Enforces RFC 8259 JSON response schema.
"""

import base64
import json
import time

import httpx

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput
from backend.app.services.models.freellm_extractor import clean_json_text
from backend.app.services.models.prompts import get_prompt_for_doctype


class DirectGeminiExtractor(BaseVisionExtractor):
    """Direct Google Gemini Vision extractor using official Generative Language API."""

    def __init__(
        self,
        name: str = "direct_gemini",
        model_id: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 25.0,
    ):
        model_name = model_id or settings.GEMINI_MODEL or "gemini-2.5-flash"
        super().__init__(name=name, model_id=model_name)
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.timeout = timeout_seconds

    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        """Call Google Gemini generateContent endpoint directly."""
        start_time = time.perf_counter()

        if not self.api_key:
            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text="",
                latency_ms=0.0,
                status="ERROR",
                error="GEMINI_API_KEY is not configured.",
            )

        prompt = get_prompt_for_doctype(doc_type)
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:generateContent?key={self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text="",
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=f"Gemini API returned HTTP {response.status_code}: {response.text}",
                )

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=response.text,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error="Gemini returned no candidates.",
                )

            parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = parts[0].get("text", "") if parts else ""
            cleaned = clean_json_text(raw_text)

            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as jde:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text=raw_text,
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=f"JSON decoding error: {jde}",
                )

            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text=raw_text,
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
                error=f"Direct Gemini timeout after {self.timeout}s",
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
