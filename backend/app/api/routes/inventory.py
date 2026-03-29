"""
Inventory and balance endpoints.

Router prefix: /api/inventory
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.analytics import RebalanceSuggestion
from app.models.balance import Balance
from app.models.exchange import Exchange
from app.schemas.inventory import (
    AssetSummary,
    BalanceSchema,
    ExchangeAllocation,
    InventorySummary,
    RebalanceSuggestionSchema,
)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


# ---------------------------------------------------------------------------
# Helper: fetch balances from DB with exchange names
# ---------------------------------------------------------------------------


async def _fetch_balances(
    db: AsyncSession,
    exchange_name: Optional[str] = None,
) -> tuple[list[tuple[Balance, str, uuid.UUID]], bool]:
    """Return (list_of_(balance, exchange_name, exchange_id), success)."""
    try:
        query = (
            select(Balance, Exchange.name, Exchange.id)
            .join(Exchange, Balance.exchange_id == Exchange.id)
        )
        if exchange_name:
            query = query.where(Exchange.name == exchange_name)
        query = query.order_by(Exchange.name, Balance.asset)

        result = await db.execute(query)
        rows = result.all()
        return [(bal, exn, exid) for bal, exn, exid in rows], True
    except Exception as exc:
        logger.debug("Failed to fetch balances: {}", exc)
        return [], False




# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/balances",
    response_model=list[BalanceSchema],
    summary="All balances across exchanges",
)
async def get_all_balances(
    db: AsyncSession = Depends(get_db),
) -> list[BalanceSchema]:
    """Return all asset balances across all configured exchanges."""

    rows, ok = await _fetch_balances(db)
    if ok and rows:
        result = []
        for bal, ex_name, _ in rows:
            schema = BalanceSchema.model_validate(bal)
            schema.exchange_name = ex_name
            result.append(schema)
        return result
    return []


@router.get(
    "/balances/{exchange}",
    response_model=list[BalanceSchema],
    summary="Balances for a specific exchange",
)
async def get_exchange_balances(
    exchange: str,
    db: AsyncSession = Depends(get_db),
) -> list[BalanceSchema]:
    """Return balances for a specific exchange."""

    rows, ok = await _fetch_balances(db, exchange_name=exchange)
    if ok and rows:
        result = []
        for bal, ex_name, _ in rows:
            schema = BalanceSchema.model_validate(bal)
            schema.exchange_name = ex_name
            result.append(schema)
        return result
    if ok and not rows:
        raise HTTPException(status_code=404, detail=f"No balances found for exchange '{exchange}'")
    return []


@router.get(
    "/allocation",
    response_model=InventorySummary,
    summary="Asset allocation breakdown",
)
async def get_allocation(
    db: AsyncSession = Depends(get_db),
) -> InventorySummary:
    """Return a full inventory summary with per-asset totals and per-exchange allocation."""

    rows, ok = await _fetch_balances(db)

    if ok and rows:
        # Build per-exchange allocations
        exchange_map: dict[str, ExchangeAllocation] = {}
        asset_map: dict[str, dict] = {}  # asset -> aggregated info
        grand_total = Decimal(0)

        for bal, ex_name, ex_id in rows:
            usd_val = Decimal(str(bal.usd_value)) if bal.usd_value else Decimal(0)
            grand_total += usd_val

            # Exchange allocation
            if ex_name not in exchange_map:
                exchange_map[ex_name] = ExchangeAllocation(
                    exchange=ex_name,
                    exchange_id=ex_id,
                    total_usd_value=Decimal(0),
                    pct_of_portfolio=Decimal(0),
                    balances=[],
                )
            alloc = exchange_map[ex_name]
            alloc.total_usd_value += usd_val
            alloc.balances.append(BalanceSchema.model_validate(bal))

            # Asset summary
            asset = bal.asset
            if asset not in asset_map:
                asset_map[asset] = {
                    "total_free": Decimal(0),
                    "total_locked": Decimal(0),
                    "total": Decimal(0),
                    "total_usd_value": Decimal(0),
                    "exchange_breakdown": {},
                }
            a = asset_map[asset]
            a["total_free"] += Decimal(str(bal.free))
            a["total_locked"] += Decimal(str(bal.locked))
            a["total"] += Decimal(str(bal.total))
            a["total_usd_value"] += usd_val
            a["exchange_breakdown"][ex_name] = Decimal(str(bal.total))

        # Calculate percentages
        allocations = list(exchange_map.values())
        for alloc in allocations:
            if grand_total > 0:
                alloc.pct_of_portfolio = min(alloc.total_usd_value / grand_total * 100, Decimal(100))

        assets = [
            AssetSummary(asset=asset, **data) for asset, data in asset_map.items()
        ]

        return InventorySummary(
            total_usd_value=grand_total,
            assets=assets,
            allocations=allocations,
            timestamp=datetime.now(timezone.utc),
        )

    return InventorySummary(
        total_usd_value=Decimal(0),
        assets=[],
        allocations=[],
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/rebalance-suggestions",
    response_model=list[RebalanceSuggestionSchema],
    summary="Get rebalance suggestions",
)
async def get_rebalance_suggestions(
    db: AsyncSession = Depends(get_db),
) -> list[RebalanceSuggestionSchema]:
    """Return current rebalance suggestions sorted by most recent."""

    try:
        result = await db.execute(
            select(RebalanceSuggestion)
            .order_by(RebalanceSuggestion.created_at.desc())
            .limit(50)
        )
        suggestions = result.scalars().all()
        if suggestions:
            return [RebalanceSuggestionSchema.model_validate(s) for s in suggestions]
    except Exception as exc:
        logger.debug("Failed to query rebalance suggestions: {}", exc)

    return []


# ---------------------------------------------------------------------------
# InventoryManager-backed endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/exposure",
    summary="Get current exposure breakdown",
)
async def get_exposure(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the current exposure breakdown from the InventoryManager,
    falling back to database if the manager has no data."""

    # Try InventoryManager first (live exchange data)
    inventory_manager = getattr(request.app.state, "inventory_manager", None)
    if inventory_manager is not None:
        exposure = inventory_manager.get_exposure()
        if exposure and exposure.get("total_value_usdt", 0) > 0:
            return exposure

    # Fallback: build exposure from database balances
    rows, ok = await _fetch_balances(db)
    if ok and rows:
        grand_total = Decimal(0)
        per_exchange: dict[str, float] = {}
        per_asset: dict[str, float] = {}

        for bal, ex_name, _ in rows:
            usd_val = Decimal(str(bal.usd_value)) if bal.usd_value else Decimal(0)
            grand_total += usd_val
            per_exchange[ex_name] = per_exchange.get(ex_name, 0) + float(usd_val)
            per_asset[bal.asset] = per_asset.get(bal.asset, 0) + float(usd_val)

        # Concentration risk: max single-asset percentage
        concentration_risk = 0.0
        if grand_total > 0:
            max_asset_val = max(per_asset.values()) if per_asset else 0
            concentration_risk = max_asset_val / float(grand_total) * 100

        return {
            "total_value_usdt": float(grand_total),
            "per_exchange": per_exchange,
            "per_asset": per_asset,
            "concentration_risk": round(concentration_risk, 2),
        }

    return {
        "total_value_usdt": 0,
        "per_exchange": {},
        "per_asset": {},
        "concentration_risk": 0,
    }


@router.get(
    "/summary",
    summary="Get inventory summary",
)
async def get_inventory_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return a comprehensive inventory summary from the InventoryManager,
    falling back to database if the manager has no data."""

    # Try InventoryManager first (live exchange data)
    inventory_manager = getattr(request.app.state, "inventory_manager", None)
    if inventory_manager is not None:
        summary = inventory_manager.get_inventory_summary()
        if summary and summary.get("total_value_usdt", 0) > 0:
            return summary

    # Fallback: build summary from database balances
    rows, ok = await _fetch_balances(db)
    if ok and rows:
        grand_total = Decimal(0)
        exchange_set: set[str] = set()
        asset_set: set[str] = set()
        stablecoin_balance = Decimal(0)
        exchange_totals: dict[str, Decimal] = {}

        stablecoins = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD"}

        for bal, ex_name, _ in rows:
            usd_val = Decimal(str(bal.usd_value)) if bal.usd_value else Decimal(0)
            grand_total += usd_val
            exchange_set.add(ex_name)
            asset_set.add(bal.asset)
            if bal.asset in stablecoins:
                stablecoin_balance += Decimal(str(bal.total))
            exchange_totals[ex_name] = exchange_totals.get(ex_name, Decimal(0)) + usd_val

        allocations = []
        for ex_name, total in exchange_totals.items():
            pct = (total / grand_total * 100) if grand_total > 0 else Decimal(0)
            allocations.append({
                "exchange": ex_name,
                "total_usd_value": float(total),
                "pct_of_portfolio": float(pct),
            })

        return {
            "total_value_usdt": float(grand_total),
            "exchange_count": len(exchange_set),
            "asset_count": len(asset_set),
            "last_refresh_at": datetime.now(timezone.utc).timestamp(),
            "stablecoin_balance": float(stablecoin_balance),
            "allocations": allocations,
        }

    return {
        "total_value_usdt": 0,
        "exchange_count": 0,
        "asset_count": 0,
        "last_refresh_at": datetime.now(timezone.utc).timestamp(),
        "stablecoin_balance": 0,
        "allocations": [],
    }
