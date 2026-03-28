"""
WebSocket message Pydantic schemas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Generic WS envelope
# ---------------------------------------------------------------------------


class WsMessage(BaseModel):
    """Generic WebSocket message envelope.

    All WebSocket frames follow this structure; the ``data`` payload
    varies by ``type`` / ``channel``.
    """

    type: str = Field(description="Message type (e.g. market, opportunity, execution, alert, system)")
    channel: str = Field(description="Subscription channel (e.g. ticker:BTC/USDT, opportunities)")
    data: Any = Field(description="Payload — structure depends on message type")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Server timestamp when the message was emitted",
    )


# ---------------------------------------------------------------------------
# Typed payloads
# ---------------------------------------------------------------------------


class WsMarketUpdate(BaseModel):
    """Real-time market data pushed over WebSocket."""

    exchange: str = Field(description="Exchange identifier")
    symbol: str = Field(description="Unified symbol (e.g. BTC/USDT)")
    bid: Decimal = Field(description="Best bid price")
    ask: Decimal = Field(description="Best ask price")
    bid_size: Optional[Decimal] = Field(default=None, description="Quantity at best bid")
    ask_size: Optional[Decimal] = Field(default=None, description="Quantity at best ask")
    last_price: Optional[Decimal] = Field(default=None, description="Last traded price")
    volume_24h: Optional[Decimal] = Field(default=None, description="24-hour trading volume")
    spread_pct: Optional[Decimal] = Field(default=None, description="Spread as percentage of mid price")
    timestamp: datetime = Field(description="Data timestamp")


class WsOpportunityUpdate(BaseModel):
    """Opportunity detected / updated event pushed over WebSocket."""

    id: str = Field(description="Opportunity UUID as string")
    strategy_type: str = Field(description="Strategy type")
    buy_exchange: Optional[str] = Field(default=None, description="Buy-side exchange")
    sell_exchange: Optional[str] = Field(default=None, description="Sell-side exchange")
    symbol: Optional[str] = Field(default=None, description="Primary symbol")
    spread_pct: Optional[Decimal] = Field(default=None, description="Raw spread percentage")
    estimated_net_profit_pct: Optional[Decimal] = Field(
        default=None, description="Estimated net profit percentage"
    )
    confidence_score: Optional[Decimal] = Field(default=None, description="0-1 confidence score")
    is_executable: bool = Field(description="Whether opportunity passes pre-trade checks")
    status: str = Field(description="Current status")
    detected_at: datetime = Field(description="Detection timestamp")


class WsExecutionUpdate(BaseModel):
    """Execution status change pushed over WebSocket."""

    id: str = Field(description="Execution plan UUID as string")
    opportunity_id: Optional[str] = Field(default=None, description="Related opportunity UUID")
    strategy_type: str = Field(description="Strategy type")
    mode: str = Field(description="Execution mode (PAPER or LIVE)")
    status: str = Field(description="Current execution status")
    planned_profit_pct: Optional[Decimal] = Field(default=None, description="Expected profit percentage")
    actual_profit_pct: Optional[Decimal] = Field(default=None, description="Realized profit percentage")
    actual_profit_usdt: Optional[Decimal] = Field(default=None, description="Realized profit in USDT")
    execution_time_ms: Optional[int] = Field(default=None, description="Execution duration in ms")
    error_message: Optional[str] = Field(default=None, description="Error if failed")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Update timestamp",
    )


class WsAlertUpdate(BaseModel):
    """Alert pushed over WebSocket."""

    id: str = Field(description="Alert UUID as string")
    alert_type: str = Field(description="Alert category")
    severity: str = Field(description="Severity level (INFO, WARNING, CRITICAL)")
    title: str = Field(description="Short alert headline")
    message: Optional[str] = Field(default=None, description="Detailed alert body")
    source: Optional[str] = Field(default=None, description="Component that generated the alert")
    created_at: datetime = Field(description="Alert creation timestamp")
