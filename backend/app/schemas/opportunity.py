"""
Arbitrage opportunity Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse, TimeRange


# ---------------------------------------------------------------------------
# Opportunity read schema (mirrors every column on the ORM model)
# ---------------------------------------------------------------------------


class ArbitrageOpportunitySchema(BaseModel):
    """Full read representation of an ArbitrageOpportunity row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Opportunity unique identifier")
    strategy_type: str = Field(description="Strategy type (CROSS_EXCHANGE, TRIANGULAR, FUTURES_SPOT)")
    symbols: Optional[list[str]] = Field(default=None, description="Symbols involved in this opportunity")
    exchanges: Optional[list[str]] = Field(default=None, description="Exchange names involved")
    buy_exchange: Optional[str] = Field(default=None, description="Exchange to buy from")
    sell_exchange: Optional[str] = Field(default=None, description="Exchange to sell on")
    buy_price: Optional[Decimal] = Field(default=None, description="Best ask on buy exchange")
    sell_price: Optional[Decimal] = Field(default=None, description="Best bid on sell exchange")
    spread_pct: Optional[Decimal] = Field(default=None, description="Raw spread percentage")
    theoretical_profit_pct: Optional[Decimal] = Field(
        default=None, description="Profit percentage before fees and slippage"
    )
    estimated_net_profit_pct: Optional[Decimal] = Field(
        default=None, description="Estimated profit percentage after fees and slippage"
    )
    estimated_slippage_pct: Optional[Decimal] = Field(
        default=None, description="Estimated slippage based on orderbook depth"
    )
    executable_quantity: Optional[Decimal] = Field(
        default=None, description="Maximum executable quantity in base asset"
    )
    executable_value_usdt: Optional[Decimal] = Field(
        default=None, description="Executable notional value in USDT"
    )
    buy_fee_pct: Optional[Decimal] = Field(default=None, description="Taker fee on buy side")
    sell_fee_pct: Optional[Decimal] = Field(default=None, description="Taker fee on sell side")
    confidence_score: Optional[Decimal] = Field(default=None, description="0-1 confidence score")
    risk_flags: Optional[dict[str, Any]] = Field(default=None, description="Risk flag names mapped to details")
    orderbook_depth_buy: Optional[Decimal] = Field(
        default=None, description="Orderbook depth on buy side (USDT)"
    )
    orderbook_depth_sell: Optional[Decimal] = Field(
        default=None, description="Orderbook depth on sell side (USDT)"
    )
    is_executable: bool = Field(description="Whether opportunity passes all pre-trade checks")
    rejection_reason: Optional[str] = Field(default=None, description="Reason the opportunity was rejected")
    detected_at: datetime = Field(description="Timestamp when opportunity was first detected")
    expired_at: Optional[datetime] = Field(default=None, description="Timestamp when opportunity expired")
    status: str = Field(description="Current status (DETECTED, EXECUTING, EXECUTED, EXPIRED, REJECTED)")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")


# ---------------------------------------------------------------------------
# List response
# ---------------------------------------------------------------------------


OpportunityListResponse = PaginatedResponse[ArbitrageOpportunitySchema]


# ---------------------------------------------------------------------------
# Filter parameters
# ---------------------------------------------------------------------------


class OpportunityFilter(BaseModel):
    """Query parameters for filtering opportunities."""

    strategy_type: Optional[str] = Field(
        default=None, description="Filter by strategy type (CROSS_EXCHANGE, TRIANGULAR, FUTURES_SPOT)"
    )
    status: Optional[str] = Field(
        default=None, description="Filter by status (DETECTED, EXECUTING, EXECUTED, EXPIRED, REJECTED)"
    )
    symbol: Optional[str] = Field(default=None, description="Filter by symbol (e.g. BTC/USDT)")
    buy_exchange: Optional[str] = Field(default=None, description="Filter by buy exchange")
    sell_exchange: Optional[str] = Field(default=None, description="Filter by sell exchange")
    is_executable: Optional[bool] = Field(default=None, description="Filter by executability flag")
    min_spread_pct: Optional[Decimal] = Field(default=None, description="Minimum spread percentage")
    min_profit_pct: Optional[Decimal] = Field(default=None, description="Minimum estimated net profit percentage")
    time_range: Optional[TimeRange] = Field(default=None, description="Filter by detection time range")
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=50, ge=1, le=500, description="Items per page")
