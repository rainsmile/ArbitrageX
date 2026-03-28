"""
Market data endpoints -- tickers, orderbooks, spreads, freshness, and arbitrage opportunities.

Router prefix: /api/market

All data is served from live MarketDataService and ArbitrageScanner via app.state.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.opportunity import ArbitrageOpportunity
from app.schemas.opportunity import ArbitrageOpportunitySchema, OpportunityListResponse

router = APIRouter(prefix="/api/market", tags=["market"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_market_data(request: Request):
    """Extract MarketDataService from app state, raise 503 if unavailable."""
    market_data = getattr(request.app.state, "market_data", None)
    if market_data is None:
        raise HTTPException(status_code=503, detail="MarketDataService is not initialized")
    return market_data


def _get_scanner(request: Request):
    """Extract ArbitrageScanner from app state, raise 503 if unavailable."""
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(status_code=503, detail="ArbitrageScanner is not initialized")
    return scanner


def _ticker_to_dict(ticker) -> dict[str, Any]:
    """Convert a StandardTicker to a JSON-serializable dict."""
    return {
        "exchange": ticker.exchange,
        "symbol": ticker.symbol,
        "bid": ticker.bid,
        "ask": ticker.ask,
        "bid_size": ticker.bid_size,
        "ask_size": ticker.ask_size,
        "last_price": ticker.last_price,
        "volume_24h": ticker.volume_24h,
        "timestamp": ticker.timestamp.isoformat() if ticker.timestamp else None,
    }


def _orderbook_to_dict(ob) -> dict[str, Any]:
    """Convert a StandardOrderbook to a JSON-serializable dict."""
    bids = [{"price": lvl.price, "quantity": lvl.quantity} for lvl in ob.bids]
    asks = [{"price": lvl.price, "quantity": lvl.quantity} for lvl in ob.asks]
    return {
        "exchange": ob.exchange,
        "symbol": ob.symbol,
        "bids": bids,
        "asks": asks,
        "best_bid": ob.best_bid,
        "best_ask": ob.best_ask,
        "spread": ob.spread,
        "mid_price": ob.mid_price,
        "timestamp": ob.timestamp.isoformat() if ob.timestamp else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/tickers",
    summary="All tickers across exchanges",
)
async def get_tickers(
    request: Request,
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g. BTC/USDT)"),
    exchange: Optional[str] = Query(None, description="Filter by exchange name"),
) -> list[dict[str, Any]]:
    """Return latest ticker data for all exchanges, optionally filtered by symbol and/or exchange."""
    market_data = _get_market_data(request)
    all_tickers = market_data.get_all_tickers()

    results: list[dict[str, Any]] = []
    for (exch, sym), ticker in all_tickers.items():
        if symbol and sym != symbol:
            continue
        if exchange and exch != exchange:
            continue
        results.append(_ticker_to_dict(ticker))

    return results


@router.get(
    "/tickers/{exchange}/{symbol:path}",
    summary="Specific ticker for exchange and symbol",
)
async def get_ticker(request: Request, exchange: str, symbol: str) -> dict[str, Any]:
    """Return the latest ticker for a specific exchange and symbol pair."""
    market_data = _get_market_data(request)
    ticker = market_data.get_ticker(exchange, symbol)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found for {exchange}/{symbol}")
    return _ticker_to_dict(ticker)


@router.get(
    "/orderbooks/{exchange}/{symbol:path}",
    summary="Orderbook for exchange and symbol",
)
async def get_orderbook(
    request: Request,
    exchange: str,
    symbol: str,
    depth: int = Query(20, ge=1, le=100, description="Number of orderbook levels"),
) -> dict[str, Any]:
    """Return the orderbook for a specific exchange and symbol."""
    market_data = _get_market_data(request)
    ob = market_data.get_orderbook(exchange, symbol)
    if ob is None:
        raise HTTPException(status_code=404, detail=f"Orderbook not found for {exchange}/{symbol}")

    result = _orderbook_to_dict(ob)
    # Trim to requested depth
    result["bids"] = result["bids"][:depth]
    result["asks"] = result["asks"][:depth]
    return result


@router.get(
    "/spreads",
    summary="Price spreads across exchanges",
)
async def get_spreads(
    request: Request,
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g. BTC/USDT)"),
) -> list[dict[str, Any]]:
    """Return cross-exchange spread comparison for monitored symbols."""
    market_data = _get_market_data(request)

    # Determine which symbols to check
    all_tickers = market_data.get_all_tickers()
    symbols_in_cache: set[str] = set()
    for (exch, sym) in all_tickers.keys():
        symbols_in_cache.add(sym)

    if symbol:
        target_symbols = [symbol] if symbol in symbols_in_cache else []
    else:
        target_symbols = sorted(symbols_in_cache)

    results: list[dict[str, Any]] = []
    for sym in target_symbols:
        spread_info = market_data.get_spread(sym)
        if spread_info is None:
            continue
        results.append({
            "symbol": spread_info.symbol,
            "best_bid_exchange": spread_info.best_bid_exchange,
            "best_bid": spread_info.best_bid,
            "best_ask_exchange": spread_info.best_ask_exchange,
            "best_ask": spread_info.best_ask,
            "spread_pct": spread_info.spread_pct,
            "timestamp": spread_info.timestamp,
        })

    return results


@router.get(
    "/freshness",
    summary="Data freshness report for all cached tickers",
)
async def get_freshness(request: Request) -> dict[str, Any]:
    """Report staleness information for every (exchange, symbol) in cache."""
    market_data = _get_market_data(request)

    now = time.time()
    entries: list[dict[str, Any]] = []
    total_stale = 0
    total_fresh = 0

    # Access the internal ticker cache via the public interface
    all_tickers = market_data.get_all_tickers()
    for (exchange, symbol) in all_tickers.keys():
        age = market_data.get_data_age(exchange, symbol)
        is_stale = market_data.is_data_stale(exchange, symbol)
        if is_stale:
            total_stale += 1
        else:
            total_fresh += 1
        entries.append({
            "exchange": exchange,
            "symbol": symbol,
            "age_seconds": round(age, 2) if age is not None else None,
            "is_stale": is_stale,
            "stale_threshold_s": market_data.stale_threshold_s,
        })

    total = total_stale + total_fresh
    return {
        "summary": {
            "total_entries": total,
            "fresh": total_fresh,
            "stale": total_stale,
            "freshness_pct": round(total_fresh / total * 100, 1) if total > 0 else 0.0,
            "stale_threshold_s": market_data.stale_threshold_s,
            "checked_at": now,
        },
        "entries": entries,
    }


@router.get(
    "/arbitrage-opportunities",
    summary="Current detected arbitrage opportunities",
)
async def get_arbitrage_opportunities(
    request: Request,
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    min_profit: Optional[float] = Query(None, ge=0, description="Minimum estimated net profit %"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return currently detected arbitrage opportunities.

    First tries the in-memory scanner results (most recent), then falls back
    to the database for historical data.
    """
    scanner = None
    try:
        scanner = _get_scanner(request)
    except HTTPException:
        pass

    # Try to get live opportunities from scanner
    opportunities: list[dict[str, Any]] = []

    if scanner is not None:
        # Trigger a scan to get fresh results
        try:
            cross_opps = await scanner.cross_exchange.scan_once()
            tri_opps = await scanner.triangular.scan_once()
            all_opps = cross_opps + tri_opps

            for opp in all_opps:
                if strategy_type and opp.strategy_type != strategy_type:
                    continue
                if min_profit is not None and opp.estimated_net_profit_pct < min_profit:
                    continue
                opportunities.append(opp.to_dict())
        except Exception as exc:
            logger.debug("Failed to get live opportunities from scanner: {}", exc)

    # If we got live results, return them
    if opportunities:
        opportunities = opportunities[:limit]
        return {
            "source": "live_scanner",
            "total": len(opportunities),
            "items": opportunities,
        }

    # Fallback: query database for historical opportunities
    try:
        query = select(ArbitrageOpportunity)

        if strategy_type:
            query = query.where(ArbitrageOpportunity.strategy_type == strategy_type)
        if min_profit is not None:
            query = query.where(ArbitrageOpportunity.estimated_net_profit_pct >= min_profit)

        query = query.order_by(ArbitrageOpportunity.detected_at.desc()).limit(limit)

        result = await db.execute(query)
        db_opportunities = result.scalars().all()

        items = []
        for o in db_opportunities:
            items.append(ArbitrageOpportunitySchema.model_validate(o).model_dump(mode="json"))

        return {
            "source": "database",
            "total": len(items),
            "items": items,
        }
    except Exception as exc:
        logger.debug("Failed to query opportunities from DB: {}", exc)
        return {
            "source": "none",
            "total": 0,
            "items": [],
        }
