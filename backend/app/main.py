"""FastAPI Application Entrypoint.

Configures CORS, lifespan hooks (DB initialization), exception handling,
and routes for Paper-to-Structured-Data Engine.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.routes_benchmark import router as benchmark_router
from backend.app.api.routes_export import router as export_router
from backend.app.api.routes_extract import router as extract_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_review import router as review_router
from backend.app.config import settings
from backend.app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler: initializes database on startup."""
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-Model Consensus OCR & Document Extraction Engine for handwritten, messy, and mixed regional script documents.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(extract_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(benchmark_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "api_v1": "/api/v1",
        "health": "/api/v1/health",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Clean JSON response on unexpected exceptions (prevents internal trace leakage)."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": str(exc)
            if settings.DEBUG
            else "An unexpected error occurred during processing.",
        },
    )
