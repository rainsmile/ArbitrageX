"""
Strategy configuration Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import PaginatedResponse


# ---------------------------------------------------------------------------
# Full read schema
# ---------------------------------------------------------------------------


class StrategyConfigSchema(BaseModel):
    """Read representation of a strategy configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Strategy config unique identifier")
    name: str = Field(description="Unique strategy name")
    strategy_type: str = Field(description="Strategy type (CROSS_EXCHANGE, TRIANGULAR, FUTURES_SPOT)")
    is_enabled: bool = Field(description="Whether this strategy is currently enabled")
    exchanges: Optional[list[str]] = Field(default=None, description="Exchange names to monitor")
    symbols: Optional[list[str]] = Field(default=None, description="Symbols to monitor")
    min_profit_threshold_pct: Optional[Decimal] = Field(
        default=None, description="Minimum net profit percentage to trigger execution"
    )
    max_order_value_usdt: Optional[Decimal] = Field(
        default=None, description="Maximum notional per execution (USDT)"
    )
    max_concurrent_executions: Optional[int] = Field(
        default=None, description="Maximum parallel execution plans"
    )
    min_depth_usdt: Optional[Decimal] = Field(
        default=None, description="Minimum orderbook depth required (USDT)"
    )
    max_slippage_pct: Optional[Decimal] = Field(
        default=None, description="Maximum tolerable slippage percentage"
    )
    scan_interval_ms: Optional[int] = Field(
        default=None, description="Opportunity scan interval in milliseconds"
    )
    blacklist_symbols: Optional[list[str]] = Field(default=None, description="Symbols to always skip")
    whitelist_symbols: Optional[list[str]] = Field(default=None, description="If set, only trade these symbols")
    custom_params: Optional[dict[str, Any]] = Field(
        default=None, description="Strategy-specific parameters"
    )
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")


# ---------------------------------------------------------------------------
# Partial update
# ---------------------------------------------------------------------------


class StrategyConfigUpdate(BaseModel):
    """Partial update payload for a strategy configuration.

    Only provided fields will be updated; ``None`` values are ignored.
    """

    name: Optional[str] = Field(default=None, description="Unique strategy name")
    strategy_type: Optional[str] = Field(
        default=None, description="Strategy type (CROSS_EXCHANGE, TRIANGULAR, FUTURES_SPOT)"
    )
    is_enabled: Optional[bool] = Field(default=None, description="Enable or disable the strategy")
    exchanges: Optional[list[str]] = Field(default=None, description="Exchange names to monitor")
    symbols: Optional[list[str]] = Field(default=None, description="Symbols to monitor")
    min_profit_threshold_pct: Optional[Decimal] = Field(
        default=None, ge=0, description="Minimum net profit percentage"
    )
    max_order_value_usdt: Optional[Decimal] = Field(
        default=None, ge=0, description="Maximum notional per execution (USDT)"
    )
    max_concurrent_executions: Optional[int] = Field(
        default=None, ge=1, description="Maximum parallel execution plans"
    )
    min_depth_usdt: Optional[Decimal] = Field(
        default=None, ge=0, description="Minimum orderbook depth required (USDT)"
    )
    max_slippage_pct: Optional[Decimal] = Field(
        default=None, ge=0, description="Maximum tolerable slippage percentage"
    )
    scan_interval_ms: Optional[int] = Field(
        default=None, ge=50, description="Opportunity scan interval in milliseconds"
    )
    blacklist_symbols: Optional[list[str]] = Field(default=None, description="Symbols to always skip")
    whitelist_symbols: Optional[list[str]] = Field(default=None, description="Only trade these symbols")
    custom_params: Optional[dict[str, Any]] = Field(
        default=None, description="Strategy-specific parameters"
    )

    @field_validator("strategy_type", mode="after")
    @classmethod
    def _valid_strategy_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"CROSS_EXCHANGE", "TRIANGULAR", "FUTURES_SPOT"}
            if v.upper() not in allowed:
                raise ValueError(f"strategy_type must be one of {allowed}")
            return v.upper()
        return v


# ---------------------------------------------------------------------------
# List response
# ---------------------------------------------------------------------------


StrategyListResponse = PaginatedResponse[StrategyConfigSchema]
