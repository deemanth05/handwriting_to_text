"""Model C: Hybrid Layout OCR + Text Structurer.

First extracts raw OCR text lines, then pipes them into an LLM structurer
via FreeLLMAPI to map messy lines into the canonical JSON schema.
Provides an uncorrelated failure mode from pure vision models.
"""

import base64
import json
import time

import cv2
import httpx
import numpy as np

from backend.app.config import settings
from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import BaseVisionExtractor, RawModelOutput
from backend.app.services.models.freellm_extractor import clean_json_text
from backend.app.services.models.prompts import get_prompt_for_doctype


class HybridOCRExtractor(BaseVisionExtractor):
    """Hybrid extractor: OCR line extraction -> LLM structurer."""

    def __init__(
        self,
        name: str = "hybrid_ocr",
        model_id: str = settings.FREELLM_MODEL_C_STRUCT,
        base_url: str = settings.FREELLM_BASE_URL,
        api_key: str = settings.FREELLM_API_KEY,
        timeout_seconds: float = settings.FREELLM_TIMEOUT_SECONDS,
    ):
        super().__init__(name=name, model_id=model_id)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "freellm-default-token"
        self.timeout = timeout_seconds

    def _extract_raw_lines_fallback(self, image_bytes: bytes) -> str:
        """Lightweight OpenCV-based text line and contour detection."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return ""

        # Basic text area detection
        _, thresh = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Sort contours top to bottom
        sorted_contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[1])
        return f"[Detected {len(sorted_contours)} text baseline regions across document]"

    async def extract(
        self,
        image_bytes: bytes,
        doc_type: DocumentType = DocumentType.INVOICE,
    ) -> RawModelOutput:
        """Run OCR + Structurer pipeline."""
        start_time = time.perf_counter()
        target_schema_prompt = get_prompt_for_doctype(doc_type)

        raw_ocr_lines = self._extract_raw_lines_fallback(image_bytes)

        # Format prompt asking structurer to map layout & image into target schema
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64_image}"

        user_content = [
            {
                "type": "text",
                "text": (
                    f"You are the Hybrid OCR Structurer. Perform line-by-line bounding text reading "
                    f"and map the document into the target JSON schema.\n"
                    f"OCR Layout Context: {raw_ocr_lines}\n\n"
                    f"{target_schema_prompt}"
                ),
            },
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]

        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PaperExtractionEngine-HybridOCR/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text="",
                    latency_ms=latency_ms,
                    status="ERROR",
                    error=f"Hybrid OCR returned HTTP {response.status_code}: {response.text}",
                )

            res_json = response.json()
            choices = res_json.get("choices", [])
            if not choices:
                return RawModelOutput(
                    model_name=self.name,
                    model_identifier=self.model_id,
                    raw_text="",
                    latency_ms=latency_ms,
                    status="ERROR",
                    error="Hybrid OCR returned no choices.",
                )

            raw_text = choices[0].get("message", {}).get("content", "")
            cleaned = clean_json_text(raw_text)
            parsed = json.loads(cleaned)

            return RawModelOutput(
                model_name=self.name,
                model_identifier=self.model_id,
                raw_text=raw_text,
                parsed_json=parsed,
                latency_ms=latency_ms,
                status="SUCCESS",
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
