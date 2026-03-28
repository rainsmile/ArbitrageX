"""
Exchange model -- represents a configured cryptocurrency exchange.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.balance import Balance
    from app.models.symbol import ExchangeSymbol


class Exchange(TimestampMixin, Base):
    __tablename__ = "exchanges"

    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="Internal exchange identifier (e.g. binance, okx)"
    )
    display_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Human-readable exchange name"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Whether this exchange is enabled for trading"
    )
    api_status: Mapped[str] = mapped_column(
        String(20), default="UNKNOWN", nullable=False, comment="REST API connectivity status"
    )
    ws_status: Mapped[str] = mapped_column(
        String(20), default="UNKNOWN", nullable=False, comment="WebSocket connectivity status"
    )
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last successful heartbeat timestamp"
    )
    config_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Exchange-specific configuration (rate limits, endpoints, etc.)"
    )

    # ---- relationships ----
    symbols: Mapped[list[ExchangeSymbol]] = relationship(
        "ExchangeSymbol", back_populates="exchange", lazy="selectin"
    )
    balances: Mapped[list[Balance]] = relationship(
        "Balance", back_populates="exchange", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_exchanges_name", "name"),
        Index("ix_exchanges_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Exchange(id={self.id!r}, name={self.name!r}, active={self.is_active})>"
