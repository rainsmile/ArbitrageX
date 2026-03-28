"""
Order endpoints -- list and detail.

Router prefix: /api/orders
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.order import Order
from app.schemas.order import OrderListResponse, OrderSchema

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get(
    "/",
    response_model=OrderListResponse,
    summary="List orders with filters",
)
async def list_orders(
    exchange: Optional[str] = Query(None, description="Filter by exchange name"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    side: Optional[str] = Query(None, description="Filter by side (BUY, SELL)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_time: Optional[datetime] = Query(None, description="Filter by submitted_at start (ISO8601)"),
    end_time: Optional[datetime] = Query(None, description="Filter by submitted_at end (ISO8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """Return a paginated list of orders with optional filters."""

    try:
        query = select(Order)
        count_query = select(func.count()).select_from(Order)

        if exchange:
            query = query.where(Order.exchange == exchange)
            count_query = count_query.where(Order.exchange == exchange)
        if symbol:
            query = query.where(Order.symbol == symbol)
            count_query = count_query.where(Order.symbol == symbol)
        if side:
            query = query.where(Order.side == side)
            count_query = count_query.where(Order.side == side)
        if status:
            query = query.where(Order.status == status)
            count_query = count_query.where(Order.status == status)
        if start_time:
            query = query.where(Order.submitted_at >= start_time)
            count_query = count_query.where(Order.submitted_at >= start_time)
        if end_time:
            query = query.where(Order.submitted_at <= end_time)
            count_query = count_query.where(Order.submitted_at <= end_time)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Order.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        orders = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return OrderListResponse(
            items=[OrderSchema.model_validate(o) for o in orders],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except Exception as exc:
        logger.debug("Failed to query orders: {}", exc)
        return OrderListResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )


@router.get(
    "/{order_id}",
    response_model=OrderSchema,
    summary="Get a specific order",
)
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> OrderSchema:
    """Return a single order by its ID."""

    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return OrderSchema.model_validate(order)
