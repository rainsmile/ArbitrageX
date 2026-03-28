"""
Simulation endpoints -- simulate arbitrage trades without real execution.

Router prefix: /api/simulate
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from app.services.scanner import OpportunityCandidate

router = APIRouter(prefix="/api/simulate", tags=["simulate"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CrossExchangeRequest(BaseModel):
    symbol: str = Field(description="Trading pair, e.g. BTC/USDT")
    buy_exchange: str = Field(description="Exchange to buy from")
    sell_exchange: str = Field(description="Exchange to sell on")
    quantity: Optional[float] = Field(default=None, ge=0, description="Quantity to trade; auto-computed if omitted")
    max_notional_usdt: Optional[float] = Field(default=10000, ge=0, description="Max notional in USDT for auto-quantity")


class TriangularRequest(BaseModel):
    exchange: str = Field(description="Exchange to execute on")
    path: list[str] = Field(description="Three symbols forming the triangular path")
    start_amount: float = Field(default=1000, ge=0, description="Starting amount in quote currency")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_market_data(request: Request):
    md = getattr(request.app.state, "market_data", None)
    if md is None:
        raise HTTPException(status_code=503, detail="MarketDataService is not initialized")
    return md


def _get_simulation(request: Request):
    sim = getattr(request.app.state, "simulation", None)
    if sim is None:
        raise HTTPException(status_code=503, detail="SimulationService is not initialized")
    return sim


def _get_scanner(request: Request):
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(status_code=503, detail="ArbitrageScanner is not initialized")
    return scanner


def _sim_result_to_dict(result) -> dict[str, Any]:
    """Convert a SimulationResult dataclass to a JSON-serializable dict."""
    legs = []
    for leg in result.legs:
        legs.append({
            "exchange": leg.exchange,
            "symbol": leg.symbol,
            "side": leg.side,
            "planned_price": leg.planned_price,
            "planned_quantity": leg.planned_quantity,
            "fill_price": leg.fill_price,
            "fill_quantity": leg.fill_quantity,
            "fee_pct": leg.fee_pct,
            "fee_usdt": leg.fee_usdt,
            "slippage_pct": leg.slippage_pct,
            "slippage_usdt": leg.slippage_usdt,
        })
    return {
        "strategy_type": result.strategy_type,
        "entry_price": result.entry_price,
        "exit_price": result.exit_price,
        "entry_value_usdt": result.entry_value_usdt,
        "exit_value_usdt": result.exit_value_usdt,
        "gross_profit_usdt": result.gross_profit_usdt,
        "total_fees_usdt": result.total_fees_usdt,
        "total_slippage_usdt": result.total_slippage_usdt,
        "net_profit_usdt": result.net_profit_usdt,
        "net_profit_pct": result.net_profit_pct,
        "feasible": result.feasible,
        "reason": result.reason,
        "legs": legs,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/cross-exchange",
    summary="Simulate a cross-exchange arbitrage trade",
)
async def simulate_cross_exchange(
    request: Request,
    body: CrossExchangeRequest,
) -> dict[str, Any]:
    """Simulate buying on one exchange and selling on another.

    If quantity is not provided, it is auto-computed from orderbook depth
    up to max_notional_usdt.
    """
    market_data = _get_market_data(request)
    simulation = _get_simulation(request)

    # Get current prices to determine quantity if needed
    buy_ticker = market_data.get_ticker(body.buy_exchange, body.symbol)
    sell_ticker = market_data.get_ticker(body.sell_exchange, body.symbol)

    if buy_ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ticker data for {body.buy_exchange}/{body.symbol}",
        )
    if sell_ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ticker data for {body.sell_exchange}/{body.symbol}",
        )

    quantity = body.quantity
    if quantity is None or quantity <= 0:
        # Auto-compute: use max_notional / ask price
        max_notional = body.max_notional_usdt or 10000
        if buy_ticker.ask > 0:
            quantity = max_notional / buy_ticker.ask
        else:
            raise HTTPException(
                status_code=400,
                detail="Cannot auto-compute quantity: ask price is zero",
            )

    # Build an OpportunityCandidate for the simulation service
    spread_pct = 0.0
    if buy_ticker.ask > 0:
        spread_pct = (sell_ticker.bid - buy_ticker.ask) / buy_ticker.ask * 100.0

    opp = OpportunityCandidate(
        strategy_type="CROSS_EXCHANGE",
        symbol=body.symbol,
        symbols=[body.symbol],
        exchanges=[body.buy_exchange, body.sell_exchange],
        buy_exchange=body.buy_exchange,
        sell_exchange=body.sell_exchange,
        buy_price=buy_ticker.ask,
        sell_price=sell_ticker.bid,
        spread_pct=spread_pct,
        theoretical_profit_pct=spread_pct,
        executable_quantity=quantity,
        executable_value_usdt=quantity * buy_ticker.ask,
    )

    result = await simulation.simulate_cross_exchange(opp)

    return {
        "request": body.model_dump(),
        "computed_quantity": quantity,
        "market_snapshot": {
            "buy_exchange_ask": buy_ticker.ask,
            "sell_exchange_bid": sell_ticker.bid,
            "raw_spread_pct": spread_pct,
        },
        "simulation": _sim_result_to_dict(result),
        "timestamp": time.time(),
    }


@router.post(
    "/triangular",
    summary="Simulate a triangular arbitrage trade",
)
async def simulate_triangular(
    request: Request,
    body: TriangularRequest,
) -> dict[str, Any]:
    """Simulate a triangular arbitrage path within a single exchange."""
    market_data = _get_market_data(request)
    simulation = _get_simulation(request)

    if len(body.path) != 3:
        raise HTTPException(status_code=400, detail="Triangular path must have exactly 3 symbols")

    # Verify all tickers exist
    tickers_snapshot: dict[str, Any] = {}
    for sym in body.path:
        ticker = market_data.get_ticker(body.exchange, sym)
        if ticker is None:
            raise HTTPException(
                status_code=404,
                detail=f"No ticker data for {body.exchange}/{sym}",
            )
        tickers_snapshot[sym] = {"bid": ticker.bid, "ask": ticker.ask}

    # Build OpportunityCandidate
    opp = OpportunityCandidate(
        strategy_type="TRIANGULAR",
        symbol=">".join(body.path),
        symbols=body.path,
        exchanges=[body.exchange],
        buy_exchange=body.exchange,
        sell_exchange=body.exchange,
        executable_value_usdt=body.start_amount,
    )

    result = await simulation.simulate_triangular(opp)

    return {
        "request": body.model_dump(),
        "market_snapshot": tickers_snapshot,
        "simulation": _sim_result_to_dict(result),
        "timestamp": time.time(),
    }


@router.post(
    "/opportunity/{opportunity_id}",
    summary="Simulate execution of a specific opportunity",
)
async def simulate_opportunity(
    request: Request,
    opportunity_id: str,
) -> dict[str, Any]:
    """Look up an opportunity from the scanner's recent list and simulate it."""
    scanner = _get_scanner(request)
    simulation = _get_simulation(request)

    # Run a fresh scan to get current opportunities
    try:
        cross_opps = await scanner.cross_exchange.scan_once()
        tri_opps = await scanner.triangular.scan_once()
        all_opps = cross_opps + tri_opps
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to scan for opportunities: {exc}")

    # Find the opportunity by ID
    target_opp = None
    for opp in all_opps:
        if opp.id == opportunity_id:
            target_opp = opp
            break

    if target_opp is None:
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity {opportunity_id} not found in recent scan results. "
                   f"Available IDs: {[o.id for o in all_opps[:10]]}",
        )

    # Run simulation based on strategy type
    if target_opp.strategy_type == "TRIANGULAR":
        result = await simulation.simulate_triangular(target_opp)
    else:
        result = await simulation.simulate_cross_exchange(target_opp)

    return {
        "opportunity": target_opp.to_dict(),
        "simulation": _sim_result_to_dict(result),
        "timestamp": time.time(),
    }


@router.get(
    "/quick-scan",
    summary="Run a single scan and simulate all found opportunities",
)
async def quick_scan(request: Request) -> dict[str, Any]:
    """Run the scanner once synchronously and return all found opportunities
    together with their simulation results. Ideal for testing and demos."""
    scanner = _get_scanner(request)
    simulation = _get_simulation(request)

    t0 = time.time()

    # Run both scanners
    try:
        cross_opps = await scanner.cross_exchange.scan_once()
    except Exception as exc:
        logger.warning("Cross-exchange scan failed in quick-scan: {}", exc)
        cross_opps = []

    try:
        tri_opps = await scanner.triangular.scan_once()
    except Exception as exc:
        logger.warning("Triangular scan failed in quick-scan: {}", exc)
        tri_opps = []

    all_opps = cross_opps + tri_opps

    # Simulate each opportunity
    results: list[dict[str, Any]] = []
    for opp in all_opps:
        try:
            if opp.strategy_type == "TRIANGULAR":
                sim_result = await simulation.simulate_triangular(opp)
            else:
                sim_result = await simulation.simulate_cross_exchange(opp)
            results.append({
                "opportunity": opp.to_dict(),
                "simulation": _sim_result_to_dict(sim_result),
            })
        except Exception as exc:
            results.append({
                "opportunity": opp.to_dict(),
                "simulation": None,
                "simulation_error": str(exc),
            })

    elapsed_ms = (time.time() - t0) * 1000.0

    return {
        "scan_duration_ms": round(elapsed_ms, 2),
        "cross_exchange_found": len(cross_opps),
        "triangular_found": len(tri_opps),
        "total_found": len(all_opps),
        "results": results,
        "timestamp": time.time(),
    }
