"""Health & Service Readiness Check Routes."""

import httpx
from fastapi import APIRouter

from backend.app.config import settings

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Basic health status of the extraction backend."""
    return {
        "status": "HEALTHY",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@router.get("/freellmapi")
async def freellmapi_health_check():
    """Verify connectivity with the local FreeLLMAPI proxy router."""
    models_url = f"{settings.FREELLM_BASE_URL.rstrip('/')}/models"
    headers = {
        "Authorization": f"Bearer {settings.FREELLM_API_KEY}",
        "User-Agent": "PaperExtractionEngine/1.0",
    }
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", [])]
                return {
                    "router_status": "ONLINE",
                    "base_url": settings.FREELLM_BASE_URL,
                    "available_models_count": len(models),
                    "sample_models": models[:5],
                }
            return {
                "router_status": "ERROR",
                "http_status": resp.status_code,
                "detail": resp.text,
            }
    except Exception as e:
        return {
            "router_status": "OFFLINE",
            "base_url": settings.FREELLM_BASE_URL,
            "error": str(e),
            "hint": "Ensure the FreeLLMAPI router is running on port 3001.",
        }
