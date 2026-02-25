"""Async engine and session factory for SQLAlchemy."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .base import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/fim_agent.db")


async def init_db() -> None:
    """Create the async engine and run ``CREATE TABLE`` for all models."""
    global _engine, _session_factory

    # Import all models so Base.metadata is fully populated before create_all.
    import fim_agent.web.models  # noqa: F401

    url = _get_database_url()
    logger.info("Initializing database: %s", url.split("@")[-1] if "@" in url else url)

    connect_args: dict = {}
    kwargs: dict = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure the data directory exists for SQLite file-based databases.
        db_path = url.split("///", 1)[-1] if "///" in url else None
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(url, connect_args=connect_args, echo=False, **kwargs)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` — intended for use with FastAPI ``Depends``."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session


async def shutdown_db() -> None:
    """Dispose of the engine and release all connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed")
        _engine = None
        _session_factory = None
