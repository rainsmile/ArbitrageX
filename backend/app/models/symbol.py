"""
ExchangeSymbol model -- trading pair configuration per exchange.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.exchange import Exchange


class ExchangeSymbol(TimestampMixin, Base):
    __tablename__ = "exchange_symbols"

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        ForeignKey("exchanges.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="Unified symbol (e.g. BTC/USDT)"
    )
    base_asset: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Base asset (e.g. BTC)"
    )
    quote_asset: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Quote asset (e.g. USDT)"
    )
    price_precision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8, comment="Decimal places for price"
    )
    quantity_precision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8, comment="Decimal places for quantity"
    )
    min_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Minimum order quantity"
    )
    max_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Maximum order quantity"
    )
    min_notional: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Minimum notional value (price * quantity)"
    )
    tick_size: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Minimum price movement"
    )
    step_size: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Minimum quantity movement"
    )
    maker_fee: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="Maker fee rate (e.g. 0.001 = 0.1%)"
    )
    taker_fee: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="Taker fee rate"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Whether this pair is enabled"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="TRADING", nullable=False, comment="Exchange-reported status"
    )

    # ---- relationships ----
    exchange: Mapped[Exchange] = relationship(
        "Exchange", back_populates="symbols"
    )

    __table_args__ = (
        Index("ix_exchange_symbols_exchange_symbol", "exchange_id", "symbol", unique=True),
        Index("ix_exchange_symbols_symbol", "symbol"),
        Index("ix_exchange_symbols_base_quote", "base_asset", "quote_asset"),
        Index("ix_exchange_symbols_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExchangeSymbol(id={self.id!r}, exchange_id={self.exchange_id!r}, "
            f"symbol={self.symbol!r}, active={self.is_active})>"
        )
