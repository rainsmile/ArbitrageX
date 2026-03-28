"""
Exchange management endpoints -- adapter status, symbols, and balances.

Router prefix: /api/exchanges
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.core.config import settings

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_exchange_factory(request: Request):
    factory = getattr(request.app.state, "exchange_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="ExchangeFactory is not initialized")
    return factory


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/status",
    summary="Status of all exchange adapters",
)
async def exchanges_status(request: Request) -> dict[str, Any]:
    """Return health status for every registered exchange adapter."""
    factory = _get_exchange_factory(request)
    adapters = factory.get_all()

    statuses: list[dict[str, Any]] = []
    for name, adapter in adapters.items():
        is_mock = name.startswith("mock")
        is_initialized = getattr(adapter, "_initialized", False)

        # Try to get symbols count
        symbols_count = 0
        health = "unknown"
        if is_initialized:
            try:
                symbols = await adapter.get_symbols()
                symbols_count = len(symbols)
                health = "healthy"
            except Exception as exc:
                health = f"error: {exc}"
                logger.debug("Health check failed for {}: {}", name, exc)
        else:
            health = "not_initialized"

        statuses.append({
            "name": name,
            "is_initialized": is_initialized,
            "is_mock": is_mock,
            "mode": "paper" if settings.trading.paper_mode else "live",
            "health": health,
            "supported_symbols_count": symbols_count,
        })

    return {
        "paper_mode": settings.trading.paper_mode,
        "total_adapters": len(adapters),
        "exchanges": statuses,
    }


@router.get(
    "/{name}/symbols",
    summary="List all symbols for a specific exchange",
)
async def exchange_symbols(request: Request, name: str) -> dict[str, Any]:
    """Return all tradeable symbols for a specific exchange adapter."""
    factory = _get_exchange_factory(request)

    try:
        adapter = factory.get(name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Exchange adapter '{name}' not found")

    is_initialized = getattr(adapter, "_initialized", False)
    if not is_initialized:
        raise HTTPException(status_code=503, detail=f"Exchange adapter '{name}' is not initialized")

    try:
        symbols = await adapter.get_symbols()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbols from {name}: {exc}")

    symbol_list = []
    for s in symbols:
        symbol_list.append({
            "symbol": s.symbol,
            "base_asset": s.base_asset,
            "quote_asset": s.quote_asset,
            "price_precision": s.price_precision,
            "quantity_precision": s.quantity_precision,
            "min_quantity": s.min_quantity,
            "max_quantity": s.max_quantity,
            "min_notional": s.min_notional,
            "tick_size": s.tick_size,
            "step_size": s.step_size,
            "is_active": s.is_active,
        })

    return {
        "exchange": name,
        "total_symbols": len(symbol_list),
        "symbols": symbol_list,
    }


@router.get(
    "/{name}/balances",
    summary="Get balances for a specific exchange",
)
async def exchange_balances(request: Request, name: str) -> dict[str, Any]:
    """Return asset balances for a specific exchange adapter.

    In paper mode, these are mock balances.
    """
    factory = _get_exchange_factory(request)

    try:
        adapter = factory.get(name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Exchange adapter '{name}' not found")

    is_initialized = getattr(adapter, "_initialized", False)
    if not is_initialized:
        raise HTTPException(status_code=503, detail=f"Exchange adapter '{name}' is not initialized")

    try:
        balances = await adapter.get_balance()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch balances from {name}: {exc}")

    balance_list = []
    total_value_estimate = 0.0
    for asset, bal in balances.items():
        entry = {
            "asset": bal.asset,
            "free": bal.free,
            "locked": bal.locked,
            "total": bal.total,
        }
        balance_list.append(entry)

    return {
        "exchange": name,
        "is_mock": name.startswith("mock"),
        "paper_mode": settings.trading.paper_mode,
        "balances": balance_list,
    }
