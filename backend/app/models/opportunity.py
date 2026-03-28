"""
ArbitrageOpportunity model -- detected arbitrage windows.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.execution import ExecutionPlan
    from app.models.risk import RiskEvent


class StrategyType(str, enum.Enum):
    CROSS_EXCHANGE = "CROSS_EXCHANGE"
    TRIANGULAR = "TRIANGULAR"
    FUTURES_SPOT = "FUTURES_SPOT"


class OpportunityStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class ArbitrageOpportunity(TimestampMixin, Base):
    __tablename__ = "arbitrage_opportunities"

    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, name="strategy_type_enum", create_constraint=True),
        nullable=False,
    )
    symbols: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="JSON array of symbols involved"
    )
    exchanges: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="JSON array of exchange names involved"
    )
    buy_exchange: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Exchange to buy from"
    )
    sell_exchange: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Exchange to sell on"
    )
    buy_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Best ask on buy exchange"
    )
    sell_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Best bid on sell exchange"
    )
    spread_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Raw spread percentage"
    )
    theoretical_profit_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Profit % before fees and slippage"
    )
    estimated_net_profit_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Estimated profit % after fees and slippage"
    )
    estimated_slippage_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Estimated slippage based on orderbook depth"
    )
    executable_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Max executable quantity in base asset"
    )
    executable_value_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Executable notional value in USDT"
    )
    buy_fee_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="Taker fee on buy side"
    )
    sell_fee_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="Taker fee on sell side"
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="0-1 confidence score"
    )
    risk_flags: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="JSON map of risk flag names to details"
    )
    orderbook_depth_buy: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Orderbook depth on buy side (USDT)"
    )
    orderbook_depth_sell: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Orderbook depth on sell side (USDT)"
    )
    is_executable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Whether opportunity passes all pre-trade checks"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Reason the opportunity was rejected"
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        comment="Timestamp when opportunity was first detected",
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Timestamp when opportunity expired"
    )
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, name="opportunity_status_enum", create_constraint=True),
        default=OpportunityStatus.DETECTED,
        nullable=False,
    )

    # ---- relationships ----
    execution_plans: Mapped[list[ExecutionPlan]] = relationship(
        "ExecutionPlan", back_populates="opportunity", lazy="selectin"
    )
    risk_events: Mapped[list[RiskEvent]] = relationship(
        "RiskEvent", back_populates="opportunity", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_opportunities_status", "status"),
        Index("ix_opportunities_strategy", "strategy_type"),
        Index("ix_opportunities_detected_at", "detected_at"),
        Index("ix_opportunities_is_executable", "is_executable"),
        Index("ix_opportunities_buy_sell_exchange", "buy_exchange", "sell_exchange"),
    )

    def __repr__(self) -> str:
        return (
            f"<ArbitrageOpportunity(id={self.id!r}, strategy={self.strategy_type.value}, "
            f"spread_pct={self.spread_pct}, status={self.status.value})>"
        )
