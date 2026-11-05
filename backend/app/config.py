"""Application Configuration & Typed Settings.

Follows 12-factor principles via pydantic-settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Central configuration for Paper-to-Structured-Data Engine."""

    APP_NAME: str = "Paper-to-Structured-Data Engine"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False

    # Server settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    # FreeLLMAPI router settings (local proxy)
    FREELLM_BASE_URL: str = "http://127.0.0.1:3001/v1"
    FREELLM_API_KEY: str = ""
    FREELLM_MODEL_A: str = "google/gemini-2.0-flash-exp:free"
    FREELLM_MODEL_B: str = "qwen/qwen-2.5-vl-72b-instruct:free"
    FREELLM_MODEL_C_STRUCT: str = "auto"
    FREELLM_TIMEOUT_SECONDS: float = 15.0

    # Fallback / Mock provider option for offline tests or when FreeLLMAPI is offline
    USE_MOCK_FALLBACK: bool = False

    # Consensus & Confidence Calibration
    CONFIDENCE_3_OF_3: float = 0.98
    CONFIDENCE_2_OF_3_VALID: float = 0.82
    CONFIDENCE_2_OF_3_INVALID: float = 0.55
    CONFIDENCE_DISAGREEMENT: float = 0.20
    CONFIDENCE_FAILED_MODEL_PENALTY: float = 0.10

    HIGH_CONFIDENCE_THRESHOLD: float = 0.90
    REVIEW_CONFIDENCE_THRESHOLD: float = 0.85

    # Deterministic Arithmetic Tolerances
    ROW_MATH_TOLERANCE: float = 0.05
    DOC_MATH_TOLERANCE: float = 0.50

    # Persistence & Storage
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR.as_posix()}/data/app.db"
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    MAX_IMAGE_SIZE_MB: int = 10

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
# Ensure upload directory exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
