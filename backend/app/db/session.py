"""
SQLAlchemy async engine and session factory.

Import ``Base`` in your model modules and ``async_session_factory`` wherever
you need a database session (most of the time through the ``get_db``
FastAPI dependency).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.db.url,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
    pool_recycle=settings.db.pool_recycle,
    echo=settings.db.echo,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base with async attribute access support."""
    pass


async def init_db() -> None:
    """Create all tables that don't exist yet.

    In production you would use Alembic migrations instead, but this is handy
    for bootstrapping a fresh database during development.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    await engine.dispose()
