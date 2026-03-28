"""
MarketDataService -- manages exchange connections, caches tickers/orderbooks,
detects stale data, and publishes MARKET_UPDATE events.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.db.redis import RedisClient
from app.exchanges.base import (
    BaseExchangeAdapter,
    StandardOrderbook,
    StandardTicker,
)
from app.exchanges.factory import ExchangeFactory


# ---------------------------------------------------------------------------
# Helper dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CachedTicker:
    """Wrapper that records when a ticker was last updated."""
    ticker: StandardTicker
    received_at: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.received_at


@dataclass(slots=True)
class CachedOrderbook:
    """Wrapper that records when an orderbook was last updated."""
    orderbook: StandardOrderbook
    received_at: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.received_at


@dataclass(slots=True)
class SpreadInfo:
    """Cross-exchange spread for a single symbol."""
    symbol: str
    best_bid_exchange: str
    best_bid: float
    best_ask_exchange: str
    best_ask: float
    spread_pct: float
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class LatencyMetrics:
    """Per-exchange latency tracking."""
    exchange: str
    last_ws_latency_ms: float = 0.0
    last_rest_latency_ms: float = 0.0
    avg_ws_latency_ms: float = 0.0
    avg_rest_latency_ms: float = 0.0
    total_ws_updates: int = 0
    total_rest_polls: int = 0


class MarketDataService:
    """Central market data hub.

    * Subscribes to tickers and orderbooks via WebSocket on each exchange adapter.
    * Falls back to REST polling when WS is unavailable.
    * Keeps an in-memory cache keyed by ``(exchange, symbol)``.
    * Publishes ``MARKET_UPDATE`` events to the event bus.
    * Detects stale data beyond a configurable threshold.
    """

    def __init__(
        self,
        event_bus: EventBus,
        exchange_factory: ExchangeFactory,
        redis_client: RedisClient,
        config: Settings | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._exchange_factory = exchange_factory
        self._redis = redis_client
        self._cfg = config or settings

        # In-memory caches: key = (exchange_name, symbol)
        self._tickers: dict[tuple[str, str], CachedTicker] = {}
        self._orderbooks: dict[tuple[str, str], CachedOrderbook] = {}

        # Latency tracking per exchange
        self._latency: dict[str, LatencyMetrics] = {}

        # Stale threshold in seconds
        self._stale_threshold_s: float = 5.0

        # REST poll interval (fallback) in seconds
        self._rest_poll_interval_s: float = self._cfg.strategy.scan_interval_ms / 1000.0

        # Background tasks
        self._ws_running = False
        self._rest_poll_task: asyncio.Task[None] | None = None
        self._stale_check_task: asyncio.Task[None] | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start WebSocket subscriptions and fallback REST polling."""
        if self._running:
            return
        self._running = True
        logger.info("MarketDataService starting")

        adapters = self._exchange_factory.get_all()
        symbols = self._cfg.strategy.enabled_pairs

        # Initialise latency metrics
        for name in adapters:
            self._latency[name] = LatencyMetrics(exchange=name)

        # Subscribe to WS tickers for all exchanges
        for name, adapter in adapters.items():
            try:
                await adapter.subscribe_tickers(
                    symbols,
                    callback=self._on_ws_ticker,
                )
                self._ws_running = True
                logger.info("WS ticker subscribed on {}", name)
            except Exception:
                logger.opt(exception=True).warning(
                    "WS ticker subscription failed on {}; will rely on REST polling", name,
                )

            # Subscribe to orderbooks for each symbol
            for symbol in symbols:
                try:
                    await adapter.subscribe_orderbook(
                        symbol,
                        callback=self._on_ws_orderbook,
                    )
                except Exception:
                    logger.opt(exception=True).warning(
                        "WS orderbook subscription failed on {} for {}", name, symbol,
                    )

        # Start background REST polling as fallback
        self._rest_poll_task = asyncio.create_task(
            self._rest_poll_loop(), name="market-data-rest-poll"
        )

        # Start stale data checker
        self._stale_check_task = asyncio.create_task(
            self._stale_check_loop(), name="market-data-stale-check"
        )

        logger.info("MarketDataService started")

    async def stop(self) -> None:
        """Gracefully shut down all background tasks."""
        self._running = False
        for task in [self._rest_poll_task, self._stale_check_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._rest_poll_task = None
        self._stale_check_task = None
        logger.info("MarketDataService stopped")

    # ------------------------------------------------------------------
    # Public getters
    # ------------------------------------------------------------------

    def get_ticker(self, exchange: str, symbol: str) -> StandardTicker | None:
        """Return the latest cached ticker, or ``None``."""
        cached = self._tickers.get((exchange, symbol))
        return cached.ticker if cached else None

    def get_orderbook(self, exchange: str, symbol: str) -> StandardOrderbook | None:
        """Return the latest cached orderbook, or ``None``."""
        cached = self._orderbooks.get((exchange, symbol))
        return cached.orderbook if cached else None

    def get_all_tickers(self) -> dict[tuple[str, str], StandardTicker]:
        """Return all cached tickers as ``{(exchange, symbol): ticker}``."""
        return {k: v.ticker for k, v in self._tickers.items()}

    def get_all_orderbooks(self) -> dict[tuple[str, str], StandardOrderbook]:
        """Return all cached orderbooks."""
        return {k: v.orderbook for k, v in self._orderbooks.items()}

    def get_spread(self, symbol: str) -> SpreadInfo | None:
        """Compute the best cross-exchange spread for *symbol*.

        Returns ``None`` if fewer than 2 exchanges have data.
        """
        tickers: list[StandardTicker] = []
        for (exch, sym), cached in self._tickers.items():
            if sym == symbol and cached.age_seconds < self._stale_threshold_s:
                tickers.append(cached.ticker)

        if len(tickers) < 2:
            return None

        # Find best bid (highest) and best ask (lowest)
        best_bid_ticker = max(tickers, key=lambda t: t.bid)
        best_ask_ticker = min(tickers, key=lambda t: t.ask)

        if best_ask_ticker.ask <= 0:
            return None

        spread_pct = (best_bid_ticker.bid - best_ask_ticker.ask) / best_ask_ticker.ask * 100.0

        return SpreadInfo(
            symbol=symbol,
            best_bid_exchange=best_bid_ticker.exchange,
            best_bid=best_bid_ticker.bid,
            best_ask_exchange=best_ask_ticker.exchange,
            best_ask=best_ask_ticker.ask,
            spread_pct=spread_pct,
        )

    def is_data_stale(self, exchange: str, symbol: str) -> bool:
        """Check whether ticker data for the given exchange/symbol is stale."""
        cached = self._tickers.get((exchange, symbol))
        if cached is None:
            return True
        return cached.age_seconds > self._stale_threshold_s

    def get_data_age(self, exchange: str, symbol: str) -> float | None:
        """Return age in seconds of the cached ticker, or ``None`` if absent."""
        cached = self._tickers.get((exchange, symbol))
        return cached.age_seconds if cached else None

    def get_latency_metrics(self) -> dict[str, LatencyMetrics]:
        """Return per-exchange latency metrics."""
        return dict(self._latency)

    @property
    def stale_threshold_s(self) -> float:
        return self._stale_threshold_s

    @stale_threshold_s.setter
    def stale_threshold_s(self, value: float) -> None:
        self._stale_threshold_s = max(0.1, value)

    # ------------------------------------------------------------------
    # WS callbacks
    # ------------------------------------------------------------------

    async def _on_ws_ticker(self, ticker: StandardTicker) -> None:
        """Handle an incoming WebSocket ticker update."""
        now = time.time()
        key = (ticker.exchange, ticker.symbol)

        self._tickers[key] = CachedTicker(ticker=ticker, received_at=now)

        # Update latency metrics
        metrics = self._latency.get(ticker.exchange)
        if metrics:
            # Approximate WS latency from ticker timestamp to now
            if ticker.timestamp:
                ws_lat = (now - ticker.timestamp.timestamp()) * 1000.0
                if ws_lat >= 0:
                    metrics.total_ws_updates += 1
                    metrics.last_ws_latency_ms = ws_lat
                    # Exponential moving average
                    alpha = 0.1
                    metrics.avg_ws_latency_ms = (
                        alpha * ws_lat + (1 - alpha) * metrics.avg_ws_latency_ms
                    )

        # Cache in Redis (fire-and-forget)
        if self._redis:
            try:
                await self._redis.set_json(
                    f"ticker:{ticker.exchange}:{ticker.symbol}",
                    {
                        "exchange": ticker.exchange,
                        "symbol": ticker.symbol,
                        "bid": ticker.bid,
                        "ask": ticker.ask,
                        "bid_size": ticker.bid_size,
                        "ask_size": ticker.ask_size,
                        "last_price": ticker.last_price,
                        "volume_24h": ticker.volume_24h,
                        "ts": now,
                    },
                    ttl_s=30,
                )
            except Exception:
                logger.opt(exception=True).debug("Redis ticker cache write failed")

        # Publish event
        await self._event_bus.publish(
            EventType.MARKET_UPDATE,
            {
                "type": "ticker",
                "exchange": ticker.exchange,
                "symbol": ticker.symbol,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "last_price": ticker.last_price,
            },
        )

    async def _on_ws_orderbook(self, orderbook: StandardOrderbook) -> None:
        """Handle an incoming WebSocket orderbook update."""
        now = time.time()
        key = (orderbook.exchange, orderbook.symbol)

        self._orderbooks[key] = CachedOrderbook(orderbook=orderbook, received_at=now)

        # Cache in Redis (lightweight summary only)
        if self._redis:
            try:
                best_bid = orderbook.best_bid
                best_ask = orderbook.best_ask
                await self._redis.set_json(
                    f"orderbook:{orderbook.exchange}:{orderbook.symbol}",
                    {
                        "exchange": orderbook.exchange,
                        "symbol": orderbook.symbol,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "bid_depth": sum(lvl.price * lvl.quantity for lvl in orderbook.bids[:10]),
                        "ask_depth": sum(lvl.price * lvl.quantity for lvl in orderbook.asks[:10]),
                        "ts": now,
                    },
                    ttl_s=30,
                )
            except Exception:
                logger.opt(exception=True).debug("Redis orderbook cache write failed")

        await self._event_bus.publish(
            EventType.MARKET_UPDATE,
            {
                "type": "orderbook",
                "exchange": orderbook.exchange,
                "symbol": orderbook.symbol,
                "best_bid": orderbook.best_bid,
                "best_ask": orderbook.best_ask,
                "spread": orderbook.spread,
            },
        )

    # ------------------------------------------------------------------
    # REST polling (fallback)
    # ------------------------------------------------------------------

    async def _rest_poll_loop(self) -> None:
        """Periodically fetch tickers via REST for exchanges where WS is unavailable."""
        logger.info("REST poll loop started (interval={:.1f}s)", self._rest_poll_interval_s)
        while self._running:
            try:
                await self._rest_poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("REST poll error")
            await asyncio.sleep(self._rest_poll_interval_s)
        logger.info("REST poll loop stopped")

    async def _rest_poll_once(self) -> None:
        """Single round of REST polling across all exchanges."""
        adapters = self._exchange_factory.get_all()
        symbols = self._cfg.strategy.enabled_pairs

        async def _poll_exchange(name: str, adapter: BaseExchangeAdapter) -> None:
            t0 = time.time()
            try:
                tickers = await adapter.get_tickers(symbols)
                elapsed_ms = (time.time() - t0) * 1000.0

                metrics = self._latency.get(name)
                if metrics:
                    metrics.total_rest_polls += 1
                    metrics.last_rest_latency_ms = elapsed_ms
                    alpha = 0.1
                    metrics.avg_rest_latency_ms = (
                        alpha * elapsed_ms + (1 - alpha) * metrics.avg_rest_latency_ms
                    )

                for ticker in tickers:
                    key = (name, ticker.symbol)
                    cached = self._tickers.get(key)
                    # Only update if we don't have fresh WS data
                    if cached is None or cached.age_seconds > 2.0:
                        self._tickers[key] = CachedTicker(ticker=ticker, received_at=time.time())

            except Exception:
                logger.opt(exception=True).warning("REST poll failed for {}", name)

        tasks = [_poll_exchange(name, adapter) for name, adapter in adapters.items()]
        await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Stale data detection
    # ------------------------------------------------------------------

    async def _stale_check_loop(self) -> None:
        """Periodically check for stale data and emit warnings."""
        while self._running:
            try:
                await asyncio.sleep(self._stale_threshold_s)
                stale_entries: list[tuple[str, str, float]] = []

                for (exchange, symbol), cached in self._tickers.items():
                    age = cached.age_seconds
                    if age > self._stale_threshold_s:
                        stale_entries.append((exchange, symbol, age))

                if stale_entries:
                    logger.warning(
                        "Stale market data detected: {} entries",
                        len(stale_entries),
                    )
                    for exchange, symbol, age in stale_entries[:5]:
                        logger.warning(
                            "  Stale: {}:{} age={:.1f}s",
                            exchange, symbol, age,
                        )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("Stale check error")
        logger.info("Stale check loop stopped")
