"""
Strategy configuration endpoints.

Router prefix: /api/strategies
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.opportunity import StrategyType
from app.models.strategy import StrategyConfig
from app.schemas.common import StatusResponse
from app.schemas.strategy import StrategyConfigSchema, StrategyConfigUpdate, StrategyListResponse

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get(
    "/",
    response_model=StrategyListResponse,
    summary="List all strategy configurations",
)
async def list_strategies(
    db: AsyncSession = Depends(get_db),
) -> StrategyListResponse:
    """Return all strategy configurations."""

    try:
        count_result = await db.execute(
            select(func.count()).select_from(StrategyConfig)
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            select(StrategyConfig).order_by(StrategyConfig.name)
        )
        strategies = result.scalars().all()

        return StrategyListResponse(
            items=[StrategyConfigSchema.model_validate(s) for s in strategies],
            total=total,
            page=1,
            page_size=max(total, 1),
            total_pages=1,
        )
    except Exception as exc:
        logger.debug("Failed to query strategies: {}", exc)
        return StrategyListResponse(
            items=[],
            total=0,
            page=1,
            page_size=50,
            total_pages=0,
        )


@router.get(
    "/{strategy_id}",
    response_model=StrategyConfigSchema,
    summary="Get a specific strategy configuration",
)
async def get_strategy(
    strategy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigSchema:
    """Return a single strategy configuration by ID."""

    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return StrategyConfigSchema.model_validate(strategy)


@router.put(
    "/{strategy_id}",
    response_model=StrategyConfigSchema,
    summary="Update a strategy configuration",
)
async def update_strategy(
    strategy_id: uuid.UUID,
    payload: StrategyConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigSchema:
    """Update fields on an existing strategy configuration.

    Only non-null fields in the request body will be applied.
    """

    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(strategy, field, value)

    await db.flush()
    await db.refresh(strategy)
    return StrategyConfigSchema.model_validate(strategy)


@router.post(
    "/{strategy_id}/enable",
    response_model=StrategyConfigSchema,
    summary="Enable a strategy",
)
async def enable_strategy(
    strategy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigSchema:
    """Enable a strategy configuration so it participates in scanning."""

    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    strategy.is_enabled = True
    await db.flush()
    await db.refresh(strategy)
    return StrategyConfigSchema.model_validate(strategy)


@router.post(
    "/{strategy_id}/disable",
    response_model=StrategyConfigSchema,
    summary="Disable a strategy",
)
async def disable_strategy(
    strategy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigSchema:
    """Disable a strategy configuration to stop it from scanning."""

    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    strategy.is_enabled = False
    await db.flush()
    await db.refresh(strategy)
    return StrategyConfigSchema.model_validate(strategy)


@router.post(
    "/seed",
    response_model=list[StrategyConfigSchema],
    summary="Seed default strategies",
)
async def seed_strategies(
    db: AsyncSession = Depends(get_db),
) -> list[StrategyConfigSchema]:
    """Seed the database with default strategy configurations if none exist.

    If strategies already exist, this is a no-op and returns the existing list.
    """

    count_result = await db.execute(
        select(func.count()).select_from(StrategyConfig)
    )
    existing_count = count_result.scalar() or 0

    if existing_count > 0:
        result = await db.execute(
            select(StrategyConfig).order_by(StrategyConfig.name)
        )
        return [StrategyConfigSchema.model_validate(s) for s in result.scalars().all()]

    defaults = [
        StrategyConfig(
            name="Cross-Exchange BTC/ETH",
            strategy_type=StrategyType.CROSS_EXCHANGE,
            is_enabled=True,
            exchanges=["binance", "okx", "bybit"],
            symbols=["BTC/USDT", "ETH/USDT"],
            min_profit_threshold_pct=0.05,
            max_order_value_usdt=5000,
            max_concurrent_executions=2,
            min_depth_usdt=500,
            max_slippage_pct=0.15,
            scan_interval_ms=500,
        ),
        StrategyConfig(
            name="Cross-Exchange Altcoins",
            strategy_type=StrategyType.CROSS_EXCHANGE,
            is_enabled=True,
            exchanges=["binance", "okx", "bybit"],
            symbols=["SOL/USDT", "XRP/USDT", "DOGE/USDT", "AVAX/USDT"],
            min_profit_threshold_pct=0.08,
            max_order_value_usdt=2000,
            max_concurrent_executions=3,
            min_depth_usdt=300,
            max_slippage_pct=0.20,
            scan_interval_ms=500,
        ),
        StrategyConfig(
            name="Triangular Binance",
            strategy_type=StrategyType.TRIANGULAR,
            is_enabled=False,
            exchanges=["binance"],
            symbols=["BTC/USDT", "ETH/BTC", "ETH/USDT"],
            min_profit_threshold_pct=0.03,
            max_order_value_usdt=3000,
            max_concurrent_executions=1,
            min_depth_usdt=1000,
            max_slippage_pct=0.10,
            scan_interval_ms=300,
        ),
    ]

    for strat in defaults:
        db.add(strat)
    await db.flush()

    result = await db.execute(
        select(StrategyConfig).order_by(StrategyConfig.name)
    )
    return [StrategyConfigSchema.model_validate(s) for s in result.scalars().all()]
