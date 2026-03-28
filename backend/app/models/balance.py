"""
Balance model -- per-exchange asset balances.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.exchange import Exchange


class Balance(TimestampMixin, Base):
    __tablename__ = "balances"

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        ForeignKey("exchanges.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Asset symbol (e.g. BTC, USDT)"
    )
    free: Mapped[float] = mapped_column(
        Numeric(28, 12), nullable=False, default=0, comment="Available balance"
    )
    locked: Mapped[float] = mapped_column(
        Numeric(28, 12), nullable=False, default=0, comment="Balance locked in open orders"
    )
    total: Mapped[float] = mapped_column(
        Numeric(28, 12), nullable=False, default=0, comment="Total balance (free + locked)"
    )
    usd_value: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Estimated USD value"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last balance refresh time",
    )

    # ---- relationships ----
    exchange: Mapped[Exchange] = relationship(
        "Exchange", back_populates="balances"
    )

    __table_args__ = (
        Index("ix_balances_exchange_asset", "exchange_id", "asset", unique=True),
        Index("ix_balances_asset", "asset"),
    )

    def __repr__(self) -> str:
        return (
            f"<Balance(id={self.id!r}, exchange_id={self.exchange_id!r}, "
            f"asset={self.asset!r}, free={self.free}, locked={self.locked})>"
        )
