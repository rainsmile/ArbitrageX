"""
Execution plan and leg Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import PaginatedResponse


# ---------------------------------------------------------------------------
# Execution leg
# ---------------------------------------------------------------------------


class ExecutionLegSchema(BaseModel):
    """Read representation of a single execution leg."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Leg unique identifier")
    execution_plan_id: uuid.UUID = Field(description="Parent execution plan UUID")
    leg_index: int = Field(description="Order of this leg within the plan (0-based)")
    exchange: str = Field(description="Exchange name for this leg")
    symbol: str = Field(description="Trading pair for this leg")
    side: str = Field(description="BUY or SELL")
    planned_price: Optional[Decimal] = Field(default=None, description="Planned entry price")
    planned_quantity: Optional[Decimal] = Field(default=None, description="Planned quantity in base asset")
    actual_price: Optional[Decimal] = Field(default=None, description="Actual fill price")
    actual_quantity: Optional[Decimal] = Field(default=None, description="Actual filled quantity")
    fee: Optional[Decimal] = Field(default=None, description="Fee amount charged")
    fee_asset: Optional[str] = Field(default=None, description="Asset in which fee was charged")
    slippage_pct: Optional[Decimal] = Field(default=None, description="Actual slippage vs planned price")
    order_id: Optional[uuid.UUID] = Field(default=None, description="Internal Order UUID")
    exchange_order_id: Optional[str] = Field(default=None, description="Exchange-assigned order ID")
    status: str = Field(description="Leg status (PENDING, SUBMITTED, PARTIAL_FILLED, FILLED, CANCELED, FAILED)")
    submitted_at: Optional[datetime] = Field(default=None, description="Order submission timestamp")
    filled_at: Optional[datetime] = Field(default=None, description="Order fill timestamp")
    error_message: Optional[str] = Field(default=None, description="Error details if the leg failed")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")


# ---------------------------------------------------------------------------
# Execution plan
# ---------------------------------------------------------------------------


class ExecutionPlanSchema(BaseModel):
    """Read representation of a full execution plan with nested legs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Execution plan unique identifier")
    opportunity_id: Optional[uuid.UUID] = Field(
        default=None, description="Related arbitrage opportunity UUID"
    )
    strategy_type: str = Field(description="Strategy type (CROSS_EXCHANGE, TRIANGULAR, FUTURES_SPOT)")
    mode: str = Field(description="Execution mode (PAPER or LIVE)")
    target_quantity: Optional[Decimal] = Field(default=None, description="Planned quantity in base asset")
    target_value_usdt: Optional[Decimal] = Field(default=None, description="Planned notional in USDT")
    planned_profit_pct: Optional[Decimal] = Field(default=None, description="Expected profit percentage")
    status: str = Field(
        description="Plan status (PENDING, SUBMITTING, PARTIAL_FILLED, FILLED, HEDGING, COMPLETED, FAILED, ABORTED)"
    )
    started_at: Optional[datetime] = Field(default=None, description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Execution completion timestamp")
    actual_profit_pct: Optional[Decimal] = Field(default=None, description="Realized profit percentage")
    actual_profit_usdt: Optional[Decimal] = Field(default=None, description="Realized profit in USDT")
    execution_time_ms: Optional[int] = Field(default=None, description="Total execution wall-clock time in ms")
    error_message: Optional[str] = Field(default=None, description="Error details if execution failed")
    metadata_json: Optional[dict[str, Any]] = Field(
        default=None, description="Arbitrary execution metadata"
    )
    legs: list[ExecutionLegSchema] = Field(default_factory=list, description="Ordered execution legs")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")


# ---------------------------------------------------------------------------
# List response
# ---------------------------------------------------------------------------


ExecutionListResponse = PaginatedResponse[ExecutionPlanSchema]


# ---------------------------------------------------------------------------
# Manual execution trigger
# ---------------------------------------------------------------------------


class ExecutionCreate(BaseModel):
    """Request body to manually trigger an execution."""

    opportunity_id: uuid.UUID = Field(description="Opportunity UUID to execute")
    mode: str = Field(default="PAPER", description="Execution mode: PAPER or LIVE")
    target_quantity: Optional[Decimal] = Field(
        default=None, ge=0, description="Override quantity in base asset (optional)"
    )
    target_value_usdt: Optional[Decimal] = Field(
        default=None, ge=0, description="Override notional in USDT (optional)"
    )

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        v = v.upper()
        if v not in ("PAPER", "LIVE"):
            raise ValueError("mode must be PAPER or LIVE")
        return v
