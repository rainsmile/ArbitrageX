"""
Inventory and balance Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Single balance row
# ---------------------------------------------------------------------------


class BalanceSchema(BaseModel):
    """Read representation of a single exchange balance entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Balance record unique identifier")
    exchange_id: uuid.UUID = Field(description="Parent exchange UUID")
    asset: str = Field(description="Asset symbol (e.g. BTC, USDT)")
    free: Decimal = Field(description="Available (unencumbered) balance")
    locked: Decimal = Field(description="Balance locked in open orders")
    total: Decimal = Field(description="Total balance (free + locked)")
    usd_value: Optional[Decimal] = Field(default=None, description="Estimated USD value")
    updated_at: datetime = Field(description="Last balance refresh time")
    created_at: datetime = Field(description="Record creation timestamp")


# ---------------------------------------------------------------------------
# Per-exchange allocation
# ---------------------------------------------------------------------------


class ExchangeAllocation(BaseModel):
    """Allocation breakdown for a single exchange."""

    exchange: str = Field(description="Exchange name")
    exchange_id: uuid.UUID = Field(description="Exchange UUID")
    total_usd_value: Decimal = Field(description="Total USD value across all assets on this exchange")
    pct_of_portfolio: Decimal = Field(ge=0, le=100, description="Percentage of total portfolio on this exchange")
    balances: list[BalanceSchema] = Field(default_factory=list, description="Individual asset balances")


# ---------------------------------------------------------------------------
# Cross-exchange asset summary
# ---------------------------------------------------------------------------


class AssetSummary(BaseModel):
    """Aggregated view of a single asset across all exchanges."""

    asset: str = Field(description="Asset symbol")
    total_free: Decimal = Field(description="Sum of free balances across all exchanges")
    total_locked: Decimal = Field(description="Sum of locked balances across all exchanges")
    total: Decimal = Field(description="Sum of total balances across all exchanges")
    total_usd_value: Optional[Decimal] = Field(default=None, description="Aggregate USD value")
    exchange_breakdown: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Mapping of exchange name to total balance for this asset",
    )


class InventorySummary(BaseModel):
    """Full inventory view: per-asset totals across exchanges plus allocations."""

    total_usd_value: Decimal = Field(description="Grand total portfolio USD value")
    assets: list[AssetSummary] = Field(default_factory=list, description="Per-asset summaries")
    allocations: list[ExchangeAllocation] = Field(
        default_factory=list, description="Per-exchange allocation breakdown"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Snapshot timestamp",
    )


# ---------------------------------------------------------------------------
# Rebalance suggestion
# ---------------------------------------------------------------------------


class RebalanceSuggestionSchema(BaseModel):
    """Read representation of a rebalance suggestion."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Suggestion unique identifier")
    asset: str = Field(description="Asset to rebalance")
    from_exchange: str = Field(description="Source exchange")
    to_exchange: str = Field(description="Destination exchange")
    suggested_quantity: Optional[Decimal] = Field(default=None, description="Recommended transfer quantity")
    reason: Optional[str] = Field(default=None, description="Why rebalance is suggested")
    status: str = Field(description="Status (PENDING, APPROVED, EXECUTED, DISMISSED)")
    created_at: datetime = Field(description="Suggestion creation timestamp")
