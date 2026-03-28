"""
StrategyConfig model -- persisted strategy parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.opportunity import StrategyType

from sqlalchemy import Enum


class StrategyConfig(TimestampMixin, Base):
    __tablename__ = "strategy_configs"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Unique strategy name"
    )
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, name="strategy_type_enum", create_constraint=False),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    exchanges: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="JSON array of exchange names to monitor"
    )
    symbols: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="JSON array of symbols to monitor"
    )
    min_profit_threshold_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="Minimum net profit % to trigger execution"
    )
    max_order_value_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Max notional per execution"
    )
    max_concurrent_executions: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=1, comment="Max parallel execution plans"
    )
    min_depth_usdt: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 8), nullable=True, comment="Min orderbook depth required (USDT)"
    )
    max_slippage_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="Max tolerable slippage %"
    )
    scan_interval_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=500, comment="Opportunity scan interval in ms"
    )
    blacklist_symbols: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="Symbols to always skip"
    )
    whitelist_symbols: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="If set, only trade these symbols"
    )
    custom_params: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Strategy-specific parameters"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_strategy_configs_strategy_type", "strategy_type"),
        Index("ix_strategy_configs_is_enabled", "is_enabled"),
        Index("ix_strategy_configs_name", "name"),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyConfig(id={self.id!r}, name={self.name!r}, "
            f"type={self.strategy_type.value}, enabled={self.is_enabled})>"
        )
