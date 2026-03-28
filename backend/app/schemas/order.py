"""
Order Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse


class OrderSchema(BaseModel):
    """Read representation of an exchange order."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Order unique identifier")
    execution_leg_id: Optional[uuid.UUID] = Field(
        default=None, description="Parent execution leg UUID"
    )
    exchange: str = Field(description="Exchange name")
    symbol: str = Field(description="Unified symbol (e.g. BTC/USDT)")
    side: str = Field(description="Order side (BUY or SELL)")
    order_type: str = Field(description="Order type (LIMIT or MARKET)")
    price: Optional[Decimal] = Field(default=None, description="Limit price (null for MARKET orders)")
    quantity: Decimal = Field(description="Requested quantity")
    filled_quantity: Optional[Decimal] = Field(default=None, description="Cumulative filled quantity")
    avg_fill_price: Optional[Decimal] = Field(default=None, description="Volume-weighted average fill price")
    fee: Optional[Decimal] = Field(default=None, description="Total fee charged")
    fee_asset: Optional[str] = Field(default=None, description="Fee denomination asset")
    status: str = Field(
        description="Order status (NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED)"
    )
    exchange_order_id: Optional[str] = Field(default=None, description="Exchange-assigned order ID")
    client_order_id: Optional[str] = Field(default=None, description="Client-generated order ID")
    submitted_at: Optional[datetime] = Field(default=None, description="Order submission timestamp")
    raw_response_json: Optional[dict[str, Any]] = Field(
        default=None, description="Raw exchange API response"
    )
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record last-update timestamp")


OrderListResponse = PaginatedResponse[OrderSchema]
