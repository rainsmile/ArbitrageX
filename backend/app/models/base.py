"""
Base model mixin providing common columns for all domain models.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, func, types
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UUIDType(types.TypeDecorator):
    """Platform-agnostic UUID type that stores as CHAR(36) in MySQL."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid.UUID(value)
        return value


class TimestampMixin:
    """Mixin that adds UUID primary key and created_at / updated_at columns."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=9000,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=9001,
    )
