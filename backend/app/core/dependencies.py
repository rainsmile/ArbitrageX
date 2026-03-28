"""
FastAPI dependency injection providers.

Usage in route handlers::

    from app.core.dependencies import get_db, get_redis, get_event_bus

    @router.get("/example")
    async def example(
        db: AsyncSession = Depends(get_db),
        redis: RedisClient = Depends(get_redis),
        bus: EventBus = Depends(get_event_bus),
    ):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.events import EventBus, event_bus
from app.db.redis import RedisClient
from app.db.session import async_session_factory


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application-wide settings singleton."""
    return settings


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session and ensure it is closed afterwards."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis(request: Request) -> RedisClient:
    """Return the ``RedisClient`` stored on the application state during
    startup.  Falls back to creating a fresh one (useful in tests)."""
    client: RedisClient | None = getattr(request.app.state, "redis", None)
    if client is None:
        raise RuntimeError("Redis client has not been initialised — check lifespan handler")
    return client


def get_event_bus() -> EventBus:
    """Return the process-global event bus singleton."""
    return event_bus
