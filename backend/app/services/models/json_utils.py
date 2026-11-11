"""Robust JSON Extraction and Parsing Helpers for Vision & Language Models.

Handles:
- Markdown fenced code blocks (```json ... ``` or ``` ... ```)
- Conversational preambles ("Here is the extracted invoice data:")
- Trailing commas or subtle formatting glitches
"""

import json
import re
from typing import Any


def clean_json_text(text: str) -> str:
    """Strip markdown code fence blocks or conversational preamble from model output."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()
    return text


def parse_llm_json(raw_text: str) -> dict[str, Any]:
    """Parse JSON from model response text with sanitization fallbacks."""
    cleaned = clean_json_text(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback 1: remove trailing commas before closing braces/brackets
        sanitized = re.sub(r",\s*([\]}])", r"\1", cleaned)
        return json.loads(sanitized)
