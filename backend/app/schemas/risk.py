"""
Risk management Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Risk rule configuration
# ---------------------------------------------------------------------------


class RiskRuleSchema(BaseModel):
    """Describes a single risk rule and its configuration."""

    name: str = Field(description="Unique risk rule name (e.g. max_position_size)")
    category: str = Field(description="Category grouping (e.g. exposure, latency, spread)")
    enabled: bool = Field(default=True, description="Whether this rule is currently active")
    threshold: Decimal = Field(description="Threshold value that triggers the rule")
    description: str = Field(default="", description="Human-readable explanation of what the rule enforces")

    @field_validator("threshold", mode="after")
    @classmethod
    def _non_negative_threshold(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Threshold must be non-negative")
        return v


# ---------------------------------------------------------------------------
# Risk event (from ORM)
# ---------------------------------------------------------------------------


class RiskEventSchema(BaseModel):
    """Read representation of a RiskEvent record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Risk event unique identifier")
    rule_name: str = Field(description="Name of the risk rule that triggered")
    rule_category: Optional[str] = Field(default=None, description="Category grouping")
    severity: str = Field(description="Severity level (INFO, WARNING, CRITICAL)")
    event_type: str = Field(description="Event type (BLOCKED, WARNING, ALERT)")
    opportunity_id: Optional[uuid.UUID] = Field(default=None, description="Related opportunity UUID")
    execution_id: Optional[uuid.UUID] = Field(default=None, description="Related execution plan UUID")
    details_json: Optional[dict[str, Any]] = Field(default=None, description="Structured event details")
    threshold_value: Optional[Decimal] = Field(default=None, description="Configured threshold that was breached")
    actual_value: Optional[Decimal] = Field(default=None, description="Actual observed value")
    message: Optional[str] = Field(default=None, description="Human-readable description")
    created_at: datetime = Field(description="Event creation timestamp")


# ---------------------------------------------------------------------------
# Exposure snapshot
# ---------------------------------------------------------------------------


class RiskExposure(BaseModel):
    """Current exposure for a single exchange + asset combination."""

    exchange: str = Field(description="Exchange name")
    asset: str = Field(description="Asset symbol (e.g. BTC, USDT)")
    amount: Decimal = Field(description="Current position amount")
    usd_value: Optional[Decimal] = Field(default=None, description="Estimated USD value of the position")
    pct_of_total: Decimal = Field(
        ge=0, le=100, description="Percentage of total portfolio value held in this position"
    )


# ---------------------------------------------------------------------------
# Aggregated risk summary
# ---------------------------------------------------------------------------


class RiskSummary(BaseModel):
    """Aggregated risk dashboard snapshot."""

    total_exposure_usd: Decimal = Field(description="Total portfolio exposure in USD")
    exposures: list[RiskExposure] = Field(default_factory=list, description="Per-exchange per-asset exposure list")
    active_rules_count: int = Field(ge=0, description="Number of enabled risk rules")
    recent_events_count: int = Field(ge=0, description="Number of risk events in the last 24 hours")
    blocked_count_24h: int = Field(ge=0, description="Opportunities blocked by risk rules in last 24 hours")
    warning_count_24h: int = Field(ge=0, description="Risk warnings issued in last 24 hours")
    max_single_exposure_pct: Decimal = Field(
        ge=0, description="Largest single-asset exposure as percentage of total"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Snapshot timestamp",
    )
