"""
Exchange and symbol Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Exchange
# ---------------------------------------------------------------------------


class ExchangeInfo(BaseModel):
    """Read-only representation of a configured exchange."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Exchange unique identifier")
    name: str = Field(description="Internal exchange identifier (e.g. binance, okx)")
    display_name: str = Field(description="Human-readable exchange name")
    is_active: bool = Field(description="Whether this exchange is enabled for trading")
    api_status: str = Field(description="REST API connectivity status")
    ws_status: str = Field(description="WebSocket connectivity status")
    last_heartbeat: Optional[datetime] = Field(default=None, description="Last successful heartbeat timestamp")
    config_json: Optional[dict[str, Any]] = Field(
        default=None, description="Exchange-specific configuration (rate limits, endpoints, etc.)"
    )
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")


class ExchangeStatus(BaseModel):
    """Lightweight health snapshot for an exchange."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Internal exchange identifier")
    display_name: str = Field(description="Human-readable exchange name")
    is_active: bool = Field(description="Whether this exchange is enabled")
    api_status: str = Field(description="REST API connectivity status")
    ws_status: str = Field(description="WebSocket connectivity status")
    last_heartbeat: Optional[datetime] = Field(default=None, description="Last successful heartbeat")
    symbols_count: int = Field(default=0, description="Number of active trading pairs")


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------


class SymbolInfo(BaseModel):
    """Trading pair configuration on a specific exchange."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Exchange-symbol unique identifier")
    exchange_id: uuid.UUID = Field(description="Parent exchange UUID")
    symbol: str = Field(description="Unified symbol (e.g. BTC/USDT)")
    base_asset: str = Field(description="Base asset (e.g. BTC)")
    quote_asset: str = Field(description="Quote asset (e.g. USDT)")
    price_precision: int = Field(description="Decimal places for price")
    quantity_precision: int = Field(description="Decimal places for quantity")
    min_quantity: Optional[Decimal] = Field(default=None, description="Minimum order quantity")
    max_quantity: Optional[Decimal] = Field(default=None, description="Maximum order quantity")
    min_notional: Optional[Decimal] = Field(default=None, description="Minimum notional value (price * quantity)")
    tick_size: Optional[Decimal] = Field(default=None, description="Minimum price movement")
    step_size: Optional[Decimal] = Field(default=None, description="Minimum quantity movement")
    maker_fee: Optional[Decimal] = Field(default=None, description="Maker fee rate (e.g. 0.001 = 0.1%)")
    taker_fee: Optional[Decimal] = Field(default=None, description="Taker fee rate")
    is_active: bool = Field(description="Whether this pair is enabled")
    status: str = Field(description="Exchange-reported status")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")
