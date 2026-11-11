"""Local & Upstream Model Runtime Discovery and Health Probing.

Detects active local AI runtimes:
- Ollama (http://127.0.0.1:11434)
- LM Studio (http://127.0.0.1:1234/v1)
- FreeLLMAPI (http://127.0.0.1:3001/v1)
- Surya Multilingual Transformer OCR (Local CPU/CUDA)
- RapidOCR ONNX (Local CPU)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from backend.app.config import settings

# Recognized vision model name substrings for local runtimes
KNOWN_VISION_PATTERNS = [
    "vision",
    "vl",
    "gemma3",
    "llava",
    "minicpm",
    "moondream",
    "internvl",
    "cogvlm",
]


class RuntimeProbe:
    """Non-blocking asynchronous health and capability discovery for AI runtimes."""

    def __init__(self):
        self.ollama_url = getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.lmstudio_url = getattr(settings, "LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        self.freellm_url = getattr(settings, "FREELLM_BASE_URL", "http://127.0.0.1:3001/v1").rstrip("/")

    async def probe_ollama(self) -> dict[str, Any]:
        """Probe local Ollama daemon for status and available vision models."""
        url = f"{self.ollama_url}/api/tags"
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(url)
            latency = (time.perf_counter() - start_time) * 1000

            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                vision_models = [
                    m for m in models
                    if any(p in m.lower() for p in KNOWN_VISION_PATTERNS)
                ]
                return {
                    "runtime": "ollama",
                    "status": "ONLINE",
                    "base_url": self.ollama_url,
                    "latency_ms": round(latency, 1),
                    "models": models,
                    "vision_models": vision_models,
                    "has_vision": len(vision_models) > 0,
                }
            return {
                "runtime": "ollama",
                "status": "ERROR",
                "base_url": self.ollama_url,
                "http_status": res.status_code,
                "has_vision": False,
            }
        except Exception as e:
            return {
                "runtime": "ollama",
                "status": "OFFLINE",
                "base_url": self.ollama_url,
                "error": str(e),
                "has_vision": False,
            }

    async def probe_lmstudio(self) -> dict[str, Any]:
        """Probe local LM Studio server for status and active loaded models."""
        url = f"{self.lmstudio_url}/models"
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(url)
            latency = (time.perf_counter() - start_time) * 1000

            if res.status_code == 200:
                data = res.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return {
                    "runtime": "lmstudio",
                    "status": "ONLINE",
                    "base_url": self.lmstudio_url,
                    "latency_ms": round(latency, 1),
                    "models": models,
                    "has_vision": len(models) > 0,
                }
            return {
                "runtime": "lmstudio",
                "status": "ERROR",
                "base_url": self.lmstudio_url,
                "http_status": res.status_code,
                "has_vision": False,
            }
        except Exception as e:
            return {
                "runtime": "lmstudio",
                "status": "OFFLINE",
                "base_url": self.lmstudio_url,
                "error": str(e),
                "has_vision": False,
            }

    async def probe_freellmapi(self) -> dict[str, Any]:
        """Probe FreeLLMAPI local proxy router."""
        url = f"{self.freellm_url}/models"
        headers = {
            "Authorization": f"Bearer {settings.FREELLM_API_KEY}",
            "User-Agent": "EnterpriseVisionEngine/1.0",
        }
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(url, headers=headers)
            latency = (time.perf_counter() - start_time) * 1000

            if res.status_code == 200:
                data = res.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return {
                    "runtime": "freellmapi",
                    "status": "ONLINE",
                    "base_url": self.freellm_url,
                    "latency_ms": round(latency, 1),
                    "models_count": len(models),
                    "has_vision": True,
                }
            return {
                "runtime": "freellmapi",
                "status": "ERROR",
                "base_url": self.freellm_url,
                "http_status": res.status_code,
                "has_vision": False,
            }
        except Exception as e:
            return {
                "runtime": "freellmapi",
                "status": "OFFLINE",
                "base_url": self.freellm_url,
                "error": str(e),
                "has_vision": False,
            }

    def probe_surya(self) -> dict[str, Any]:
        """Probe local Surya OCR availability."""
        enabled = getattr(settings, "ENABLE_SURYA_LOCAL", True)
        if not enabled:
            return {"runtime": "surya_local", "status": "DISABLED", "engine": "surya-ocr"}
        try:
            import surya  # noqa: F401
            return {
                "runtime": "surya_local",
                "status": "ONLINE",
                "engine": "surya-ocr",
                "languages": getattr(settings, "SURYA_LANGS", ["en", "hi"]),
            }
        except Exception as e:
            return {
                "runtime": "surya_local",
                "status": "UNAVAILABLE",
                "engine": "surya-ocr",
                "error": str(e),
            }

    def probe_rapidocr(self) -> dict[str, Any]:
        """Probe local RapidOCR availability."""
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa: F401
            return {
                "runtime": "rapidocr_local",
                "status": "ONLINE",
                "engine": "rapidocr-onnxruntime",
            }
        except Exception as e:
            return {
                "runtime": "rapidocr_local",
                "status": "UNAVAILABLE",
                "engine": "rapidocr-onnxruntime",
                "error": str(e),
            }

    async def probe_all(self) -> dict[str, Any]:
        """Probe all local and upstream runtimes concurrently."""
        ollama_res, lmstudio_res, freellm_res = await asyncio.gather(
            self.probe_ollama(),
            self.probe_lmstudio(),
            self.probe_freellmapi(),
        )
        surya_res = self.probe_surya()
        rapidocr_res = self.probe_rapidocr()

        return {
            "timestamp": time.time(),
            "runtimes": {
                "ollama": ollama_res,
                "lmstudio": lmstudio_res,
                "freellm": freellm_res,
                "surya_local": surya_res,
                "rapidocr_local": rapidocr_res,
            },
        }


runtime_probe = RuntimeProbe()
