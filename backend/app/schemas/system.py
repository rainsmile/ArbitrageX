"""
System health, metrics, and event Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------


class SystemHealth(BaseModel):
    """Top-level system health check response."""

    status: str = Field(description="Overall health status (healthy, degraded, unhealthy)")
    database: str = Field(description="Database connectivity status")
    redis: str = Field(description="Redis connectivity status")
    exchanges: dict[str, str] = Field(
        default_factory=dict,
        description="Per-exchange connectivity status",
    )
    uptime_seconds: int = Field(ge=0, description="Process uptime in seconds")
    version: str = Field(default="", description="Application version string")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Health check timestamp",
    )


# ---------------------------------------------------------------------------
# System metrics
# ---------------------------------------------------------------------------


class SystemMetrics(BaseModel):
    """Operational metrics snapshot."""

    scan_rate: Decimal = Field(description="Opportunity scans per second")
    opportunity_rate: Decimal = Field(description="Opportunities detected per minute")
    execution_rate: Decimal = Field(description="Executions triggered per minute")
    success_rate: Decimal = Field(ge=0, le=100, description="Execution success rate as percentage")
    avg_profit: Decimal = Field(description="Average profit per successful trade (USDT)")
    avg_slippage: Decimal = Field(description="Average slippage percentage across recent trades")
    risk_block_rate: Decimal = Field(
        ge=0, le=100, description="Percentage of opportunities blocked by risk rules"
    )
    uptime: int = Field(ge=0, description="Process uptime in seconds")
    active_strategies: int = Field(ge=0, description="Number of enabled strategies")
    active_exchanges: int = Field(ge=0, description="Number of active exchange connections")
    pending_executions: int = Field(ge=0, description="Executions currently in progress")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Metrics snapshot timestamp",
    )


# ---------------------------------------------------------------------------
# WebSocket connection status
# ---------------------------------------------------------------------------


class WsStatus(BaseModel):
    """Per-exchange WebSocket connection status."""

    exchange: str = Field(description="Exchange name")
    connected: bool = Field(description="Whether the WebSocket connection is active")
    subscribed_channels: list[str] = Field(
        default_factory=list, description="List of subscribed channel names"
    )
    last_message_at: Optional[datetime] = Field(
        default=None, description="Timestamp of the last received message"
    )
    reconnect_count: int = Field(default=0, ge=0, description="Number of reconnections since startup")
    latency_ms: Optional[int] = Field(
        default=None, ge=0, description="Estimated round-trip latency in milliseconds"
    )


# ---------------------------------------------------------------------------
# System event (from ORM)
# ---------------------------------------------------------------------------


class SystemEventSchema(BaseModel):
    """Read representation of a system event record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Event unique identifier")
    event_type: str = Field(description="Event category (e.g. STARTUP, SHUTDOWN, ERROR)")
    source: Optional[str] = Field(default=None, description="Component that emitted the event")
    message: Optional[str] = Field(default=None, description="Human-readable description")
    details_json: Optional[dict[str, Any]] = Field(default=None, description="Structured event data")
    severity: str = Field(description="Severity level (INFO, WARNING, CRITICAL)")
    created_at: datetime = Field(description="Event creation timestamp")
