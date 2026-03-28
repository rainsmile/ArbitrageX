"""
Analytics models -- PnL tracking and rebalance suggestions.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.opportunity import StrategyType
from app.models.execution import ExecutionMode

if TYPE_CHECKING:
    from app.models.execution import ExecutionPlan


class RebalanceStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    DISMISSED = "DISMISSED"


class PnlRecord(TimestampMixin, Base):
    __tablename__ = "pnl_records"

    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUIDType(),
        ForeignKey("execution_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, name="strategy_type_enum", create_constraint=False),
        nullable=False,
    )
    exchange_buy: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Buy-side exchange"
    )
    exchange_sell: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Sell-side exchange"
    )
    symbol: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="Traded symbol"
    )
    gross_profit_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Gross profit before fees"
    )
    fees_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Total fees in USDT"
    )
    net_profit_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Net profit after fees"
    )
    slippage_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Slippage cost in USDT"
    )
    execution_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="End-to-end execution time"
    )
    mode: Mapped[ExecutionMode] = mapped_column(
        Enum(ExecutionMode, name="execution_mode_enum", create_constraint=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # ---- relationships ----
    execution: Mapped[Optional[ExecutionPlan]] = relationship(
        "ExecutionPlan", back_populates="pnl_records"
    )

    __table_args__ = (
        Index("ix_pnl_records_execution", "execution_id"),
        Index("ix_pnl_records_strategy", "strategy_type"),
        Index("ix_pnl_records_symbol", "symbol"),
        Index("ix_pnl_records_mode", "mode"),
        Index("ix_pnl_records_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PnlRecord(id={self.id!r}, symbol={self.symbol!r}, "
            f"net_profit_usdt={self.net_profit_usdt}, mode={self.mode.value})>"
        )


class RebalanceSuggestion(TimestampMixin, Base):
    __tablename__ = "rebalance_suggestions"

    asset: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Asset to rebalance"
    )
    from_exchange: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Source exchange"
    )
    to_exchange: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Destination exchange"
    )
    suggested_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Recommended transfer quantity"
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Why rebalance is suggested"
    )
    status: Mapped[RebalanceStatus] = mapped_column(
        Enum(RebalanceStatus, name="rebalance_status_enum", create_constraint=True),
        default=RebalanceStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_rebalance_suggestions_asset", "asset"),
        Index("ix_rebalance_suggestions_status", "status"),
        Index("ix_rebalance_suggestions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<RebalanceSuggestion(id={self.id!r}, asset={self.asset!r}, "
            f"{self.from_exchange} -> {self.to_exchange}, status={self.status.value})>"
        )
