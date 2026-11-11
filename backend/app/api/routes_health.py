"""Health & Service Readiness Check Routes."""

from fastapi import APIRouter

from backend.app.config import settings
from backend.app.services.models.runtime_probe import runtime_probe

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


@router.get("/runtimes")
async def runtimes_health_check():
    """Verify connectivity and capability of all local and upstream model runtimes."""
    report = await runtime_probe.probe_all()
    from backend.app.services.ensemble import ensemble_dispatcher
    report["circuit_breakers"] = ensemble_dispatcher.get_circuit_breaker_telemetry()
    return report


@router.get("/freellmapi")
async def freellmapi_health_check():
    """Verify connectivity with the local FreeLLMAPI proxy router."""
    return await runtime_probe.probe_freellmapi()
