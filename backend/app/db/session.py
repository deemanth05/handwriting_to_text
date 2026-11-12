"""Database Session & Connection Management."""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config import settings
from backend.app.db.models import Base

# Ensure parent directory for sqlite database exists
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite+aiosqlite:///"):
    db_file_path = db_url.replace("sqlite+aiosqlite:///", "")
    Path(db_file_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe non-destructive column addition for page_count if table already exists
        try:
            await conn.execute(text("ALTER TABLE documents ADD COLUMN page_count INTEGER DEFAULT 1"))
        except Exception:
            pass  # Column already exists


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
