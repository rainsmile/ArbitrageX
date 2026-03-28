"""
Market data models -- real-time tick and orderbook snapshot storage.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin


class MarketTick(TimestampMixin, Base):
    __tablename__ = "market_ticks"

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), nullable=False, comment="Exchange UUID (denormalized for speed)"
    )
    symbol: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="Unified symbol (e.g. BTC/USDT)"
    )
    bid: Mapped[float] = mapped_column(
        Numeric(28, 12), nullable=False, comment="Best bid price"
    )
    ask: Mapped[float] = mapped_column(
        Numeric(28, 12), nullable=False, comment="Best ask price"
    )
    bid_size: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Best bid quantity"
    )
    ask_size: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Best ask quantity"
    )
    last_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Last traded price"
    )
    volume_24h: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="24-hour trading volume"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        comment="Exchange-reported or local capture timestamp",
    )

    __table_args__ = (
        Index("ix_market_ticks_exchange_symbol", "exchange_id", "symbol"),
        Index("ix_market_ticks_symbol_ts", "symbol", "timestamp"),
        Index("ix_market_ticks_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketTick(id={self.id!r}, exchange_id={self.exchange_id!r}, "
            f"symbol={self.symbol!r}, bid={self.bid}, ask={self.ask})>"
        )


class OrderbookSnapshot(TimestampMixin, Base):
    __tablename__ = "orderbook_snapshots"

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), nullable=False, comment="Exchange UUID (denormalized for speed)"
    )
    symbol: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="Unified symbol"
    )
    bids_json: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="Array of [price, qty] bid levels"
    )
    asks_json: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="Array of [price, qty] ask levels"
    )
    depth_levels: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Number of depth levels captured"
    )
    spread: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Best ask - best bid"
    )
    mid_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="(Best bid + best ask) / 2"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        comment="Snapshot capture timestamp",
    )

    __table_args__ = (
        Index("ix_orderbook_snapshots_exchange_symbol", "exchange_id", "symbol"),
        Index("ix_orderbook_snapshots_symbol_ts", "symbol", "timestamp"),
        Index("ix_orderbook_snapshots_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrderbookSnapshot(id={self.id!r}, exchange_id={self.exchange_id!r}, "
            f"symbol={self.symbol!r}, spread={self.spread})>"
        )
