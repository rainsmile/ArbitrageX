"""
Live trading control API routes.

Endpoints for managing trading modes, live status, permissions,
pre-order validation, and daily notional tracking.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import settings

router = APIRouter(prefix="/api/live", tags=["live"])


@router.get("/status")
async def get_live_status(request: Request) -> dict[str, Any]:
    """Get current live trading status including mode, permissions, daily limits."""
    guardrails = getattr(request.app.state, "live_guardrails", None)
    if not guardrails:
        return {
            "live_trading_enabled": False,
            "trading_mode": "paper",
            "message": "Live guardrails not initialized",
        }
    return guardrails.get_live_status()


@router.get("/permissions")
async def get_permissions(request: Request) -> dict[str, Any]:
    """Get current mode permissions and capabilities."""
    guardrails = getattr(request.app.state, "live_guardrails", None)
    if not guardrails:
        return {"error": "Live guardrails not initialized"}
    return guardrails.get_permissions()


@router.get("/mode")
async def get_current_mode(request: Request) -> dict[str, Any]:
    """Get current trading mode."""
    guardrails = getattr(request.app.state, "live_guardrails", None)
    if not guardrails:
        return {"mode": "paper", "capabilities": {}}
    return {
        "mode": guardrails.current_mode.value,
        "capabilities": {
            "can_read_public_data": guardrails.capabilities.can_read_public_data,
            "can_read_account_data": guardrails.capabilities.can_read_account_data,
            "can_place_orders": guardrails.capabilities.can_place_orders,
            "can_auto_execute": guardrails.capabilities.can_auto_execute,
            "max_single_order_usdt": guardrails.capabilities.max_single_order_usdt,
            "max_daily_notional_usdt": guardrails.capabilities.max_daily_notional_usdt,
            "audit_level": guardrails.capabilities.audit_level,
        },
    }


@router.post("/mode")
async def set_trading_mode(request: Request) -> dict[str, Any]:
    """Change the trading mode. Requires explicit confirmation for live modes.

    Body: {"mode": "paper"|"read_only"|"live_small"|"live", "changed_by": "admin"}
    """
    body = await request.json()
    mode_str = body.get("mode", "")
    changed_by = body.get("changed_by", "api")

    guardrails = getattr(request.app.state, "live_guardrails", None)
    if not guardrails:
        return JSONResponse(
            status_code=503,
            content={"error": "Live guardrails not initialized"},
        )

    try:
        from app.core.trading_modes import TradingMode

        mode = TradingMode(mode_str)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Invalid mode: {mode_str}",
                "valid_modes": [
                    "mock",
                    "read_only",
                    "paper",
                    "simulation",
                    "live_small",
                    "live",
                ],
            },
        )

    # Safety: require explicit confirmation for live modes
    if mode in (TradingMode.LIVE_SMALL, TradingMode.LIVE):
        confirm = body.get("confirm", False)
        if not confirm:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Switching to {mode.value} requires explicit confirmation",
                    "hint": "Add 'confirm': true to the request body",
                },
            )

    try:
        await guardrails.set_mode(mode, changed_by=changed_by)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )

    return {
        "success": True,
        "mode": guardrails.current_mode.value,
        "changed_by": changed_by,
        "message": f"Trading mode changed to {mode.value}",
    }


@router.post("/validate-order")
async def validate_pre_order(request: Request) -> dict[str, Any]:
    """Run pre-order validation without actually placing an order.

    Body: {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "quantity": 0.001,
        "price": 60000.0,
        "strategy_type": "CROSS_EXCHANGE"
    }
    """
    body = await request.json()
    guardrails = getattr(request.app.state, "live_guardrails", None)
    if not guardrails:
        return JSONResponse(
            status_code=503,
            content={"error": "Live guardrails not initialized"},
        )

    exchange = body.get("exchange", "")
    symbol = body.get("symbol", "")
    side = body.get("side", "BUY")
    price = body.get("price", 0.0)
    quantity = body.get("quantity", 0.0)
    strategy_type = body.get("strategy_type", "")

    check = await guardrails.validate_pre_order(
        exchange=exchange,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        strategy_type=strategy_type,
    )

    status_code = 200 if check.approved else 403
    return JSONResponse(status_code=status_code, content=check.to_dict())


@router.get("/daily-usage")
async def get_daily_usage(request: Request) -> dict[str, Any]:
    """Get daily notional usage stats."""
    guardrails = getattr(request.app.state, "live_guardrails", None)
    if not guardrails:
        return {"error": "Live guardrails not initialized"}

    status = guardrails.get_live_status()
    return {
        "daily_notional": status.get("daily_notional", {}),
        "limits": {
            "max_daily_per_exchange_usdt": guardrails._cfg.live.live_max_daily_per_exchange_usdt,
            "max_daily_per_symbol_usdt": guardrails._cfg.live.live_max_daily_per_symbol_usdt,
            "max_daily_total_usdt": guardrails._cfg.live.live_max_daily_total_usdt,
        },
    }


@router.get("/orders")
async def get_live_orders(request: Request) -> dict[str, Any]:
    """Get active and recent live orders from the order tracker."""
    tracker = getattr(request.app.state, "order_tracker", None)
    if not tracker:
        return {"active": [], "recent_completed": [], "metrics": {}}

    active = [o.to_dict() for o in tracker.get_active_orders()]
    recent = [o.to_dict() for o in tracker.get_recent_completed(limit=20)]

    return {
        "active": active,
        "recent_completed": recent,
        "metrics": {
            "total_orders_tracked": tracker.metrics.total_orders_tracked,
            "active_orders": tracker.metrics.active_orders,
            "total_filled": tracker.metrics.total_filled,
            "total_failed": tracker.metrics.total_failed,
            "total_cancelled": tracker.metrics.total_cancelled,
        },
    }


@router.get("/orders/{tracking_id}")
async def get_live_order(request: Request, tracking_id: str) -> dict[str, Any]:
    """Get a specific tracked order by tracking ID."""
    tracker = getattr(request.app.state, "order_tracker", None)
    if not tracker:
        return JSONResponse(
            status_code=503, content={"error": "Order tracker not initialized"}
        )

    order = tracker.get_order(tracking_id)
    if not order:
        return JSONResponse(
            status_code=404, content={"error": f"Order {tracking_id} not found"}
        )

    result = order.to_dict()
    result["history"] = order.history
    return result


@router.get("/reconciliation")
async def get_reconciliation_results(request: Request) -> dict[str, Any]:
    """Get recent reconciliation results."""
    tracker = getattr(request.app.state, "order_tracker", None)
    if not tracker:
        return {"results": [], "mismatches": []}

    results = [r.to_dict() for r in tracker.get_reconciliation_results(limit=50)]
    mismatches = [r.to_dict() for r in tracker.get_mismatches()]

    return {
        "results": results,
        "mismatches": mismatches,
        "metrics": {
            "total_reconciliation_runs": tracker.metrics.total_reconciliation_runs,
            "total_mismatches": tracker.metrics.total_reconciliation_mismatches,
            "last_reconciliation_at": tracker.metrics.last_reconciliation_at,
        },
    }


@router.post("/reconciliation/trigger")
async def trigger_reconciliation(request: Request) -> dict[str, Any]:
    """Manually trigger a reconciliation run."""
    tracker = getattr(request.app.state, "order_tracker", None)
    if not tracker:
        return JSONResponse(
            status_code=503, content={"error": "Order tracker not initialized"}
        )

    results = await tracker.run_reconciliation()
    return {
        "success": True,
        "checked": len(results),
        "mismatches": sum(1 for r in results if not r.is_consistent),
        "results": [r.to_dict() for r in results],
    }


# ---------------------------------------------------------------------------
# Auto-execution control
# ---------------------------------------------------------------------------


@router.get("/auto-execution")
async def get_auto_execution_status() -> dict[str, Any]:
    """Get current auto-execution settings."""
    return {
        "enabled": settings.live.allow_auto_execution,
        "trading_mode": settings.live.trading_mode,
        "require_manual_confirmation": settings.live.require_manual_confirmation,
        "trade_size_usdt": settings.live.paper_trade_size_usdt,
    }


@router.post("/auto-execution")
async def set_auto_execution(request: Request) -> dict[str, Any]:
    """Toggle auto-execution on/off, and optionally set trade size.

    Body: {"enabled": true|false, "trade_size_usdt": 1000}
    """
    body = await request.json()
    enabled = body.get("enabled")
    trade_size = body.get("trade_size_usdt")

    if enabled is not None:
        settings.live.allow_auto_execution = bool(enabled)
        settings.live.require_manual_confirmation = not bool(enabled)
        logger.info("Auto-execution toggled: enabled={}", settings.live.allow_auto_execution)

    if trade_size is not None:
        trade_size = float(trade_size)
        if trade_size <= 0:
            return JSONResponse(
                status_code=400,
                content={"error": "trade_size_usdt must be > 0"},
            )
        settings.live.paper_trade_size_usdt = trade_size
        logger.info("Paper trade size set to: {} USDT", trade_size)

    return {
        "success": True,
        "enabled": settings.live.allow_auto_execution,
        "trading_mode": settings.live.trading_mode,
        "trade_size_usdt": settings.live.paper_trade_size_usdt,
    }
