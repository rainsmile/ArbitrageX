"""
Order model -- individual exchange orders.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.execution import ExecutionLeg


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, enum.Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    execution_leg_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUIDType(),
        ForeignKey("execution_legs.id", ondelete="SET NULL"),
        nullable=True,
    )
    exchange: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Exchange name"
    )
    symbol: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="Unified symbol"
    )
    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, name="order_side_enum", create_constraint=True),
        nullable=False,
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type_enum", create_constraint=True),
        nullable=False,
    )
    price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Limit price (null for MARKET)"
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(28, 12), nullable=False, comment="Requested quantity"
    )
    filled_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, default=0, comment="Cumulative filled quantity"
    )
    avg_fill_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Volume-weighted avg fill price"
    )
    fee: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Total fee charged"
    )
    fee_asset: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Fee denomination asset"
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum", create_constraint=True),
        default=OrderStatus.NEW,
        nullable=False,
    )
    exchange_order_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Exchange-assigned order ID"
    )
    client_order_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Client-generated order ID"
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    raw_response_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Raw exchange API response"
    )

    # ---- relationships ----
    execution_leg: Mapped[Optional[ExecutionLeg]] = relationship(
        "ExecutionLeg", back_populates="orders"
    )

    __table_args__ = (
        Index("ix_orders_exchange_symbol", "exchange", "symbol"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_exchange_order_id", "exchange_order_id"),
        Index("ix_orders_client_order_id", "client_order_id"),
        Index("ix_orders_submitted_at", "submitted_at"),
        Index("ix_orders_execution_leg", "execution_leg_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id!r}, exchange={self.exchange!r}, symbol={self.symbol!r}, "
            f"side={self.side.value}, type={self.order_type.value}, status={self.status.value})>"
        )
