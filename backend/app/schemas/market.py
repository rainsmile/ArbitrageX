"""
Market data Pydantic schemas -- tickers, orderbooks, and spread info.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Ticker
# ---------------------------------------------------------------------------


class Ticker(BaseModel):
    """Real-time best-bid/ask snapshot for a single exchange + symbol."""

    model_config = ConfigDict(from_attributes=True)

    exchange: str = Field(description="Exchange identifier")
    symbol: str = Field(description="Unified symbol (e.g. BTC/USDT)")
    bid: Decimal = Field(description="Best bid price")
    ask: Decimal = Field(description="Best ask price")
    bid_size: Optional[Decimal] = Field(default=None, description="Quantity at best bid")
    ask_size: Optional[Decimal] = Field(default=None, description="Quantity at best ask")
    last_price: Optional[Decimal] = Field(default=None, description="Last traded price")
    volume_24h: Optional[Decimal] = Field(default=None, description="24-hour trading volume in base asset")
    timestamp: datetime = Field(description="Exchange-reported or local capture timestamp")

    @field_validator("bid", "ask", mode="after")
    @classmethod
    def _positive_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Price must be positive")
        return v


# ---------------------------------------------------------------------------
# Orderbook
# ---------------------------------------------------------------------------


class OrderbookLevel(BaseModel):
    """Single price level in an orderbook."""

    price: Decimal = Field(description="Price at this level")
    quantity: Decimal = Field(description="Aggregate quantity at this level")
    total: Decimal = Field(description="Cumulative notional (price * quantity)")

    @field_validator("price", "quantity", mode="after")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


class Orderbook(BaseModel):
    """Full orderbook snapshot for a single exchange + symbol."""

    model_config = ConfigDict(from_attributes=True)

    exchange: str = Field(description="Exchange identifier")
    symbol: str = Field(description="Unified symbol")
    bids: list[OrderbookLevel] = Field(default_factory=list, description="Bid levels sorted best-first (descending)")
    asks: list[OrderbookLevel] = Field(default_factory=list, description="Ask levels sorted best-first (ascending)")
    spread: Optional[Decimal] = Field(default=None, description="Best ask minus best bid")
    spread_pct: Optional[Decimal] = Field(default=None, description="Spread as percentage of mid price")
    mid_price: Optional[Decimal] = Field(default=None, description="(Best bid + best ask) / 2")
    timestamp: datetime = Field(description="Snapshot capture timestamp")


# ---------------------------------------------------------------------------
# Spread comparison across exchanges
# ---------------------------------------------------------------------------


class SpreadInfo(BaseModel):
    """Cross-exchange spread summary for a single symbol."""

    symbol: str = Field(description="Unified symbol (e.g. BTC/USDT)")
    exchanges: dict[str, Decimal] = Field(
        description="Mapping of exchange name to mid-price (or best bid/ask) for comparison"
    )
    best_bid_exchange: str = Field(description="Exchange with the highest bid (best place to sell)")
    best_ask_exchange: str = Field(description="Exchange with the lowest ask (best place to buy)")
    spread_pct: Decimal = Field(description="Percentage spread between best bid and best ask across exchanges")
    potential_profit_pct: Decimal = Field(
        description="Estimated profit percentage after accounting for typical fees"
    )
