"""
Execution models -- plans and individual legs of arbitrage executions.
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
    Integer,
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
from app.models.opportunity import StrategyType

if TYPE_CHECKING:
    from app.models.analytics import PnlRecord
    from app.models.opportunity import ArbitrageOpportunity
    from app.models.order import Order
    from app.models.risk import RiskEvent


class ExecutionMode(str, enum.Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ExecutionPlanStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTING = "SUBMITTING"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    FILLED = "FILLED"
    HEDGING = "HEDGING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class LegSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class LegStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


class ExecutionPlan(TimestampMixin, Base):
    __tablename__ = "execution_plans"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        ForeignKey("arbitrage_opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, name="strategy_type_enum", create_constraint=False),
        nullable=False,
    )
    mode: Mapped[ExecutionMode] = mapped_column(
        Enum(ExecutionMode, name="execution_mode_enum", create_constraint=True),
        nullable=False,
        comment="PAPER or LIVE trading mode",
    )
    target_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Planned quantity in base asset"
    )
    target_value_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Planned notional in USDT"
    )
    planned_profit_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Expected profit %"
    )
    status: Mapped[ExecutionPlanStatus] = mapped_column(
        Enum(ExecutionPlanStatus, name="execution_plan_status_enum", create_constraint=True),
        default=ExecutionPlanStatus.PENDING,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_profit_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Realized profit %"
    )
    actual_profit_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Realized profit in USDT"
    )
    execution_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Total execution wall-clock time in ms"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Arbitrary execution metadata"
    )

    # ---- relationships ----
    opportunity: Mapped[Optional[ArbitrageOpportunity]] = relationship(
        "ArbitrageOpportunity", back_populates="execution_plans"
    )
    legs: Mapped[list[ExecutionLeg]] = relationship(
        "ExecutionLeg", back_populates="execution_plan", lazy="selectin",
        order_by="ExecutionLeg.leg_index",
    )
    risk_events: Mapped[list[RiskEvent]] = relationship(
        "RiskEvent", back_populates="execution", lazy="selectin"
    )
    pnl_records: Mapped[list[PnlRecord]] = relationship(
        "PnlRecord", back_populates="execution", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_execution_plans_status", "status"),
        Index("ix_execution_plans_opportunity", "opportunity_id"),
        Index("ix_execution_plans_mode", "mode"),
        Index("ix_execution_plans_started_at", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExecutionPlan(id={self.id!r}, strategy={self.strategy_type.value}, "
            f"mode={self.mode.value}, status={self.status.value})>"
        )


class ExecutionLeg(TimestampMixin, Base):
    __tablename__ = "execution_legs"

    execution_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(),
        ForeignKey("execution_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    leg_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Order of this leg within the plan (0-based)"
    )
    exchange: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Exchange name for this leg"
    )
    symbol: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="Trading pair for this leg"
    )
    side: Mapped[LegSide] = mapped_column(
        Enum(LegSide, name="leg_side_enum", create_constraint=True),
        nullable=False,
    )
    planned_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True
    )
    planned_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True
    )
    actual_price: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True
    )
    actual_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True
    )
    fee: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Fee amount"
    )
    fee_asset: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Asset in which fee was charged"
    )
    slippage_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 6), nullable=True, comment="Actual slippage vs planned price"
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUIDType(), nullable=True, comment="Internal Order UUID"
    )
    exchange_order_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Exchange-assigned order ID"
    )
    status: Mapped[LegStatus] = mapped_column(
        Enum(LegStatus, name="leg_status_enum", create_constraint=True),
        default=LegStatus.PENDING,
        nullable=False,
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    filled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # ---- relationships ----
    execution_plan: Mapped[ExecutionPlan] = relationship(
        "ExecutionPlan", back_populates="legs"
    )
    orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="execution_leg", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_execution_legs_plan", "execution_plan_id"),
        Index("ix_execution_legs_status", "status"),
        Index("ix_execution_legs_exchange_symbol", "exchange", "symbol"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExecutionLeg(id={self.id!r}, leg_index={self.leg_index}, "
            f"exchange={self.exchange!r}, side={self.side.value}, status={self.status.value})>"
        )
