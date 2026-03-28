"""
ArbitrageScanner -- scans for cross-exchange and triangular arbitrage opportunities.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.exchanges.base import OrderbookLevel, StandardOrderbook, StandardTicker
from app.exchanges.factory import ExchangeFactory
from app.services.market_data import MarketDataService


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OpportunityCandidate:
    """Lightweight in-memory representation of a detected opportunity before DB persistence."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    strategy_type: str = "CROSS_EXCHANGE"
    symbol: str = ""
    symbols: list[str] = field(default_factory=list)
    exchanges: list[str] = field(default_factory=list)
    buy_exchange: str = ""
    sell_exchange: str = ""
    buy_price: float = 0.0
    sell_price: float = 0.0
    spread_pct: float = 0.0
    theoretical_profit_pct: float = 0.0
    estimated_net_profit_pct: float = 0.0
    estimated_slippage_pct: float = 0.0
    executable_quantity: float = 0.0
    executable_value_usdt: float = 0.0
    buy_fee_pct: float = 0.0
    sell_fee_pct: float = 0.0
    orderbook_depth_buy: float = 0.0
    orderbook_depth_sell: float = 0.0
    confidence_score: float = 0.0
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "strategy_type": self.strategy_type,
            "symbol": self.symbol,
            "symbols": self.symbols,
            "exchanges": self.exchanges,
            "buy_exchange": self.buy_exchange,
            "sell_exchange": self.sell_exchange,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "spread_pct": self.spread_pct,
            "theoretical_profit_pct": self.theoretical_profit_pct,
            "estimated_net_profit_pct": self.estimated_net_profit_pct,
            "estimated_slippage_pct": self.estimated_slippage_pct,
            "executable_quantity": self.executable_quantity,
            "executable_value_usdt": self.executable_value_usdt,
            "buy_fee_pct": self.buy_fee_pct,
            "sell_fee_pct": self.sell_fee_pct,
            "orderbook_depth_buy": self.orderbook_depth_buy,
            "orderbook_depth_sell": self.orderbook_depth_sell,
            "confidence_score": self.confidence_score,
            "detected_at": self.detected_at,
        }


@dataclass(slots=True)
class ScanMetrics:
    """Tracks scanner performance."""
    total_scans: int = 0
    total_opportunities_found: int = 0
    last_scan_duration_ms: float = 0.0
    avg_scan_duration_ms: float = 0.0
    last_scan_at: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_executable_quantity(
    buy_orderbook: StandardOrderbook,
    sell_orderbook: StandardOrderbook,
    max_value_usdt: float,
) -> tuple[float, float, float, float]:
    """Walk the orderbook to find the executable quantity and average prices.

    Returns (quantity, avg_buy_price, avg_sell_price, slippage_pct).
    """
    # Buy side: walk the asks (lowest first)
    buy_qty = 0.0
    buy_cost = 0.0
    for level in buy_orderbook.asks:
        if level.price <= 0 or level.quantity <= 0:
            continue
        remaining_value = max_value_usdt - buy_cost
        if remaining_value <= 0:
            break
        fillable_qty = min(level.quantity, remaining_value / level.price)
        buy_qty += fillable_qty
        buy_cost += fillable_qty * level.price

    # Sell side: walk the bids (highest first)
    sell_qty = 0.0
    sell_revenue = 0.0
    for level in sell_orderbook.bids:
        if level.price <= 0 or level.quantity <= 0:
            continue
        remaining_qty = buy_qty - sell_qty
        if remaining_qty <= 0:
            break
        fillable_qty = min(level.quantity, remaining_qty)
        sell_qty += fillable_qty
        sell_revenue += fillable_qty * level.price

    # Constrain to the minimum of both sides
    executable_qty = min(buy_qty, sell_qty)
    if executable_qty <= 0:
        return 0.0, 0.0, 0.0, 0.0

    avg_buy_price = buy_cost / buy_qty if buy_qty > 0 else 0.0
    avg_sell_price = sell_revenue / sell_qty if sell_qty > 0 else 0.0

    # Slippage: difference between top-of-book and volume-weighted average
    top_ask = buy_orderbook.best_ask
    top_bid = sell_orderbook.best_bid
    buy_slippage = (avg_buy_price - top_ask) / top_ask * 100.0 if top_ask > 0 else 0.0
    sell_slippage = (top_bid - avg_sell_price) / top_bid * 100.0 if top_bid > 0 else 0.0
    total_slippage = buy_slippage + sell_slippage

    return executable_qty, avg_buy_price, avg_sell_price, total_slippage


def _compute_orderbook_depth_usdt(levels: list[OrderbookLevel]) -> float:
    """Sum notional value of orderbook levels."""
    return sum(lvl.price * lvl.quantity for lvl in levels if lvl.price > 0)


# ---------------------------------------------------------------------------
# CrossExchangeScanner
# ---------------------------------------------------------------------------

class CrossExchangeScanner:
    """Scans price differences across exchanges for the same symbol."""

    def __init__(
        self,
        market_data: MarketDataService,
        exchange_factory: ExchangeFactory,
        event_bus: EventBus,
        config: Settings | None = None,
    ) -> None:
        self._market_data = market_data
        self._exchange_factory = exchange_factory
        self._event_bus = event_bus
        self._cfg = config or settings
        self._metrics = ScanMetrics()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_opportunities: list[OpportunityCandidate] = []

        # Default fee assumption when exchange doesn't report fees
        self._default_taker_fee_pct = 0.1

        # Minimum net profit to emit an opportunity
        self._min_profit_pct = self._cfg.risk.min_profit_threshold_pct
        self._max_order_value = self._cfg.risk.max_order_value_usdt
        self._min_depth_usdt = self._cfg.strategy.min_depth_usdt

    @property
    def metrics(self) -> ScanMetrics:
        return self._metrics

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scan_loop(), name="cross-exchange-scanner")
        logger.info("CrossExchangeScanner started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("CrossExchangeScanner stopped")

    async def _scan_loop(self) -> None:
        interval_s = self._cfg.strategy.scan_interval_ms / 1000.0
        while self._running:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("CrossExchange scan error")
            await asyncio.sleep(interval_s)

    async def scan_once(self) -> list[OpportunityCandidate]:
        """Execute a single scan pass. Returns found opportunities."""
        t0 = time.time()
        self._metrics.total_scans += 1
        self._metrics.last_scan_at = t0
        opportunities: list[OpportunityCandidate] = []

        all_tickers = self._market_data.get_all_tickers()
        if not all_tickers:
            return opportunities

        # Group tickers by symbol
        by_symbol: dict[str, list[StandardTicker]] = defaultdict(list)
        for (exchange, symbol), ticker in all_tickers.items():
            # Skip stale data
            if not self._market_data.is_data_stale(exchange, symbol):
                by_symbol[symbol].append(ticker)

        adapters = self._exchange_factory.get_all()

        for symbol, tickers in by_symbol.items():
            if len(tickers) < 2:
                continue

            # Find the best bid (highest) and best ask (lowest) across exchanges
            best_bid_ticker = max(tickers, key=lambda t: t.bid if t.bid > 0 else 0)
            best_ask_ticker = min(
                tickers,
                key=lambda t: t.ask if t.ask > 0 else float("inf"),
            )

            if best_bid_ticker.bid <= 0 or best_ask_ticker.ask <= 0:
                continue
            if best_bid_ticker.exchange == best_ask_ticker.exchange:
                continue

            # Theoretical profit (before fees/slippage)
            theoretical_profit_pct = (
                (best_bid_ticker.bid - best_ask_ticker.ask)
                / best_ask_ticker.ask
                * 100.0
            )

            if theoretical_profit_pct <= 0:
                continue

            # Get fees for both sides
            buy_fee_pct = self._default_taker_fee_pct
            sell_fee_pct = self._default_taker_fee_pct

            buy_adapter = adapters.get(best_ask_ticker.exchange)
            sell_adapter = adapters.get(best_bid_ticker.exchange)

            if buy_adapter:
                try:
                    fees = await buy_adapter.get_fees(symbol)
                    buy_fee_pct = fees.get("taker", self._default_taker_fee_pct) * 100.0
                except Exception:
                    pass

            if sell_adapter:
                try:
                    fees = await sell_adapter.get_fees(symbol)
                    sell_fee_pct = fees.get("taker", self._default_taker_fee_pct) * 100.0
                except Exception:
                    pass

            # Net profit after fees (before slippage)
            net_after_fees = theoretical_profit_pct - buy_fee_pct - sell_fee_pct

            if net_after_fees <= 0:
                continue

            # Fetch orderbooks for depth analysis
            buy_ob = self._market_data.get_orderbook(best_ask_ticker.exchange, symbol)
            sell_ob = self._market_data.get_orderbook(best_bid_ticker.exchange, symbol)

            executable_qty = 0.0
            avg_buy_price = best_ask_ticker.ask
            avg_sell_price = best_bid_ticker.bid
            slippage_pct = 0.0
            ob_depth_buy = 0.0
            ob_depth_sell = 0.0

            if buy_ob and sell_ob:
                ob_depth_buy = _compute_orderbook_depth_usdt(buy_ob.asks[:10])
                ob_depth_sell = _compute_orderbook_depth_usdt(sell_ob.bids[:10])

                if ob_depth_buy < self._min_depth_usdt or ob_depth_sell < self._min_depth_usdt:
                    continue

                executable_qty, avg_buy_price, avg_sell_price, slippage_pct = (
                    _compute_executable_quantity(buy_ob, sell_ob, self._max_order_value)
                )

            if executable_qty <= 0:
                # If no orderbook, use ticker size as estimate
                executable_qty = min(
                    best_ask_ticker.ask_size if best_ask_ticker.ask_size > 0 else 0.001,
                    best_bid_ticker.bid_size if best_bid_ticker.bid_size > 0 else 0.001,
                )

            # Final net profit after fees and slippage
            estimated_net_profit_pct = net_after_fees - slippage_pct
            if estimated_net_profit_pct < self._min_profit_pct:
                continue

            executable_value = executable_qty * avg_buy_price

            # Confidence score based on depth, spread stability, and profit margin
            depth_factor = min(1.0, min(ob_depth_buy, ob_depth_sell) / (self._min_depth_usdt * 10))
            profit_factor = min(1.0, estimated_net_profit_pct / 1.0)
            confidence = (depth_factor * 0.5 + profit_factor * 0.5)

            opp = OpportunityCandidate(
                strategy_type="CROSS_EXCHANGE",
                symbol=symbol,
                symbols=[symbol],
                exchanges=[best_ask_ticker.exchange, best_bid_ticker.exchange],
                buy_exchange=best_ask_ticker.exchange,
                sell_exchange=best_bid_ticker.exchange,
                buy_price=avg_buy_price,
                sell_price=avg_sell_price,
                spread_pct=theoretical_profit_pct,
                theoretical_profit_pct=theoretical_profit_pct,
                estimated_net_profit_pct=estimated_net_profit_pct,
                estimated_slippage_pct=slippage_pct,
                executable_quantity=executable_qty,
                executable_value_usdt=executable_value,
                buy_fee_pct=buy_fee_pct,
                sell_fee_pct=sell_fee_pct,
                orderbook_depth_buy=ob_depth_buy,
                orderbook_depth_sell=ob_depth_sell,
                confidence_score=confidence,
            )
            opportunities.append(opp)

            self._metrics.total_opportunities_found += 1

            await self._event_bus.publish(
                EventType.OPPORTUNITY_FOUND,
                opp.to_dict(),
            )
            logger.info(
                "Cross-exchange opportunity: {} buy@{}({:.2f}) sell@{}({:.2f}) net={:.4f}%",
                symbol,
                opp.buy_exchange, opp.buy_price,
                opp.sell_exchange, opp.sell_price,
                opp.estimated_net_profit_pct,
            )

        elapsed_ms = (time.time() - t0) * 1000.0
        self._metrics.last_scan_duration_ms = elapsed_ms
        alpha = 0.1
        self._metrics.avg_scan_duration_ms = (
            alpha * elapsed_ms + (1 - alpha) * self._metrics.avg_scan_duration_ms
        )

        self._last_opportunities = opportunities
        return opportunities


# ---------------------------------------------------------------------------
# TriangularScanner
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TriangularPath:
    """A single triangular arbitrage path: A -> B -> C -> A."""
    exchange: str
    leg1_symbol: str  # e.g. BTC/USDT (buy BTC with USDT)
    leg1_side: str     # BUY or SELL
    leg2_symbol: str  # e.g. ETH/BTC (buy ETH with BTC)
    leg2_side: str
    leg3_symbol: str  # e.g. ETH/USDT (sell ETH for USDT)
    leg3_side: str
    base_asset: str    # Starting asset, e.g. USDT


class TriangularScanner:
    """Scans for triangular arbitrage paths within a single exchange."""

    def __init__(
        self,
        market_data: MarketDataService,
        exchange_factory: ExchangeFactory,
        event_bus: EventBus,
        config: Settings | None = None,
    ) -> None:
        self._market_data = market_data
        self._exchange_factory = exchange_factory
        self._event_bus = event_bus
        self._cfg = config or settings
        self._metrics = ScanMetrics()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_opportunities: list[OpportunityCandidate] = []

        self._default_taker_fee_pct = 0.1
        self._min_profit_pct = self._cfg.risk.min_profit_threshold_pct

        # Precomputed triangular paths per exchange
        self._paths: dict[str, list[TriangularPath]] = {}

    @property
    def metrics(self) -> ScanMetrics:
        return self._metrics

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._build_paths()
        self._task = asyncio.create_task(self._scan_loop(), name="triangular-scanner")
        logger.info("TriangularScanner started ({} paths)", sum(len(v) for v in self._paths.values()))

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("TriangularScanner stopped")

    def _build_paths(self) -> None:
        """Enumerate valid triangular paths from the configured symbols."""
        symbols = self._cfg.strategy.enabled_pairs
        exchanges = list(self._exchange_factory.get_all().keys())

        # Parse symbols into (base, quote) pairs
        pair_set: set[str] = set(symbols)

        # Build adjacency: asset -> list of (other_asset, symbol, side_to_get_other)
        # If symbol = X/Y, buying means spend Y to get X, selling means spend X to get Y
        adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for sym in symbols:
            parts = sym.split("/")
            if len(parts) != 2:
                continue
            base, quote = parts
            # From quote, buy base via this symbol
            adjacency[quote].append((base, sym, "BUY"))
            # From base, sell to get quote via this symbol
            adjacency[base].append((quote, sym, "SELL"))

        # Find triangular cycles starting and ending with the same asset
        # We want paths of length 3: A -> B -> C -> A
        for exchange in exchanges:
            paths_for_exchange: list[TriangularPath] = []
            start_assets = {"USDT", "BTC", "ETH"}  # Common base currencies

            for start in start_assets:
                if start not in adjacency:
                    continue
                # First leg: start -> mid1
                for mid1, sym1, side1 in adjacency[start]:
                    # Second leg: mid1 -> mid2
                    for mid2, sym2, side2 in adjacency[mid1]:
                        if mid2 == start:
                            # Skip 2-hop cycles (that's just a round-trip)
                            continue
                        # Third leg: mid2 -> start
                        for end_asset, sym3, side3 in adjacency[mid2]:
                            if end_asset == start:
                                # Valid triangular path found
                                path = TriangularPath(
                                    exchange=exchange,
                                    leg1_symbol=sym1,
                                    leg1_side=side1,
                                    leg2_symbol=sym2,
                                    leg2_side=side2,
                                    leg3_symbol=sym3,
                                    leg3_side=side3,
                                    base_asset=start,
                                )
                                paths_for_exchange.append(path)

            self._paths[exchange] = paths_for_exchange

    async def _scan_loop(self) -> None:
        interval_s = self._cfg.strategy.scan_interval_ms / 1000.0
        while self._running:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("Triangular scan error")
            await asyncio.sleep(interval_s)

    def _get_effective_price(
        self, ticker: StandardTicker, side: str
    ) -> float:
        """Return the price you'd pay/receive for a given side."""
        if side == "BUY":
            return ticker.ask if ticker.ask > 0 else 0.0
        return ticker.bid if ticker.bid > 0 else 0.0

    async def scan_once(self) -> list[OpportunityCandidate]:
        """Single scan pass for triangular opportunities."""
        t0 = time.time()
        self._metrics.total_scans += 1
        self._metrics.last_scan_at = t0
        opportunities: list[OpportunityCandidate] = []

        all_tickers = self._market_data.get_all_tickers()
        if not all_tickers:
            return opportunities

        for exchange, paths in self._paths.items():
            for path in paths:
                # Get tickers for all 3 legs
                t1 = all_tickers.get((exchange, path.leg1_symbol))
                t2 = all_tickers.get((exchange, path.leg2_symbol))
                t3 = all_tickers.get((exchange, path.leg3_symbol))

                if not t1 or not t2 or not t3:
                    continue

                # Check freshness
                if (
                    self._market_data.is_data_stale(exchange, path.leg1_symbol)
                    or self._market_data.is_data_stale(exchange, path.leg2_symbol)
                    or self._market_data.is_data_stale(exchange, path.leg3_symbol)
                ):
                    continue

                # Calculate implied rate through the triangle
                # Start with 1 unit of base_asset
                # Leg 1: base -> asset1
                p1 = self._get_effective_price(t1, path.leg1_side)
                p2 = self._get_effective_price(t2, path.leg2_side)
                p3 = self._get_effective_price(t3, path.leg3_side)

                if p1 <= 0 or p2 <= 0 or p3 <= 0:
                    continue

                # Calculate how much we end up with
                amount = 1.0  # Start with 1 unit of base_asset

                # Leg 1
                if path.leg1_side == "BUY":
                    # Spend base_asset at ask price to get base of leg1_symbol
                    amount = amount / p1
                else:
                    # Sell base of leg1_symbol at bid price to get quote
                    amount = amount * p1

                # Leg 2
                if path.leg2_side == "BUY":
                    amount = amount / p2
                else:
                    amount = amount * p2

                # Leg 3
                if path.leg3_side == "BUY":
                    amount = amount / p3
                else:
                    amount = amount * p3

                # Theoretical profit before fees
                theoretical_profit_pct = (amount - 1.0) * 100.0

                if theoretical_profit_pct <= 0:
                    continue

                # 3 legs of taker fees
                total_fee_pct = self._default_taker_fee_pct * 3
                net_profit_pct = theoretical_profit_pct - total_fee_pct

                if net_profit_pct < self._min_profit_pct:
                    continue

                opp = OpportunityCandidate(
                    strategy_type="TRIANGULAR",
                    symbol=f"{path.leg1_symbol}>{path.leg2_symbol}>{path.leg3_symbol}",
                    symbols=[path.leg1_symbol, path.leg2_symbol, path.leg3_symbol],
                    exchanges=[exchange],
                    buy_exchange=exchange,
                    sell_exchange=exchange,
                    buy_price=p1,
                    sell_price=p3,
                    spread_pct=theoretical_profit_pct,
                    theoretical_profit_pct=theoretical_profit_pct,
                    estimated_net_profit_pct=net_profit_pct,
                    estimated_slippage_pct=0.0,
                    executable_quantity=0.0,
                    executable_value_usdt=0.0,
                    buy_fee_pct=total_fee_pct,
                    sell_fee_pct=0.0,
                    confidence_score=min(1.0, net_profit_pct / 1.0) * 0.7,
                )
                opportunities.append(opp)
                self._metrics.total_opportunities_found += 1

                await self._event_bus.publish(
                    EventType.OPPORTUNITY_FOUND,
                    opp.to_dict(),
                )
                logger.info(
                    "Triangular opportunity on {}: {} net={:.4f}%",
                    exchange, opp.symbol, net_profit_pct,
                )

        elapsed_ms = (time.time() - t0) * 1000.0
        self._metrics.last_scan_duration_ms = elapsed_ms
        alpha = 0.1
        self._metrics.avg_scan_duration_ms = (
            alpha * elapsed_ms + (1 - alpha) * self._metrics.avg_scan_duration_ms
        )

        self._last_opportunities = opportunities
        return opportunities


# ---------------------------------------------------------------------------
# ArbitrageScanner (composite)
# ---------------------------------------------------------------------------

class ArbitrageScanner:
    """Composite scanner that runs both cross-exchange and triangular scanners."""

    def __init__(
        self,
        market_data: MarketDataService,
        exchange_factory: ExchangeFactory,
        event_bus: EventBus,
        config: Settings | None = None,
    ) -> None:
        self.cross_exchange = CrossExchangeScanner(
            market_data=market_data,
            exchange_factory=exchange_factory,
            event_bus=event_bus,
            config=config,
        )
        self.triangular = TriangularScanner(
            market_data=market_data,
            exchange_factory=exchange_factory,
            event_bus=event_bus,
            config=config,
        )

    async def start(self) -> None:
        await self.cross_exchange.start()
        await self.triangular.start()
        logger.info("ArbitrageScanner started (cross-exchange + triangular)")

    async def stop(self) -> None:
        await self.cross_exchange.stop()
        await self.triangular.stop()
        logger.info("ArbitrageScanner stopped")

    async def scan_once(self) -> list[OpportunityCandidate]:
        """Run a single scan pass on all sub-scanners and return combined results."""
        results: list[OpportunityCandidate] = []
        try:
            cross = await self.cross_exchange.scan_once()
            results.extend(cross)
        except Exception:
            logger.opt(exception=True).warning("Cross-exchange scan_once failed")
        try:
            tri = await self.triangular.scan_once()
            results.extend(tri)
        except Exception:
            logger.opt(exception=True).warning("Triangular scan_once failed")
        # Sort by net profit descending
        results.sort(key=lambda o: o.estimated_net_profit_pct, reverse=True)
        return results

    @property
    def metrics(self) -> dict[str, ScanMetrics]:
        return {
            "cross_exchange": self.cross_exchange.metrics,
            "triangular": self.triangular.metrics,
        }

    @property
    def is_running(self) -> bool:
        return self.cross_exchange._running or self.triangular._running

    @property
    def recent_opportunities(self) -> list[OpportunityCandidate]:
        """Return opportunities from the latest scan of all sub-scanners."""
        opps: list[OpportunityCandidate] = []
        opps.extend(getattr(self.cross_exchange, '_last_opportunities', []))
        opps.extend(getattr(self.triangular, '_last_opportunities', []))
        return opps
