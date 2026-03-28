"""Tests for MarketDataService -- caching and freshness tracking.

These tests exercise the in-memory cache and spread computation logic
without requiring real exchange connections, Redis, or WebSockets.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.events import EventBus
from app.exchanges.base import (
    OrderbookLevel,
    StandardOrderbook,
    StandardTicker,
)
from app.services.market_data import (
    CachedOrderbook,
    CachedTicker,
    MarketDataService,
    SpreadInfo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ticker(exchange: str, symbol: str, bid: float, ask: float) -> StandardTicker:
    return StandardTicker(
        exchange=exchange,
        symbol=symbol,
        bid=bid,
        ask=ask,
        bid_size=1.0,
        ask_size=1.0,
        last_price=(bid + ask) / 2.0,
        volume_24h=10_000.0,
    )


def _make_orderbook(
    exchange: str,
    symbol: str,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> StandardOrderbook:
    return StandardOrderbook(
        exchange=exchange,
        symbol=symbol,
        bids=[OrderbookLevel(price=p, quantity=q) for p, q in bids],
        asks=[OrderbookLevel(price=p, quantity=q) for p, q in asks],
    )


def _make_service() -> MarketDataService:
    """Create a MarketDataService with mocked dependencies."""
    event_bus = EventBus()
    factory = MagicMock()
    factory.get_all.return_value = {}
    redis_client = MagicMock()
    redis_client.set_json = AsyncMock()

    cfg = Settings(
        strategy={
            "enabled_pairs": ["BTC/USDT", "ETH/USDT"],
            "scan_interval_ms": 500,
        },
    )

    svc = MarketDataService(
        event_bus=event_bus,
        exchange_factory=factory,
        redis_client=redis_client,
        config=cfg,
    )
    return svc


# =====================================================================
# Ticker caching
# =====================================================================

class TestTickerCache:

    def test_cache_stores_ticker(self):
        """After inserting a cached ticker, get_ticker returns it."""
        svc = _make_service()
        ticker = _make_ticker("binance", "BTC/USDT", bid=60_000, ask=60_010)

        # Directly populate the cache (simulating WS callback effect)
        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=ticker, received_at=time.time(),
        )

        result = svc.get_ticker("binance", "BTC/USDT")
        assert result is not None
        assert result.bid == 60_000
        assert result.ask == 60_010
        assert result.exchange == "binance"
        assert result.symbol == "BTC/USDT"

    def test_get_ticker_returns_none_for_missing(self):
        """Querying a non-existent key returns None."""
        svc = _make_service()
        result = svc.get_ticker("nonexistent", "BTC/USDT")
        assert result is None

    def test_get_all_tickers(self):
        """get_all_tickers returns all cached entries."""
        svc = _make_service()

        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", 60_000, 60_010),
            received_at=time.time(),
        )
        svc._tickers[("okx", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("okx", "BTC/USDT", 60_050, 60_060),
            received_at=time.time(),
        )

        all_tickers = svc.get_all_tickers()
        assert len(all_tickers) == 2
        assert ("binance", "BTC/USDT") in all_tickers
        assert ("okx", "BTC/USDT") in all_tickers


# =====================================================================
# Orderbook caching
# =====================================================================

class TestOrderbookCache:

    def test_cache_stores_orderbook(self):
        """After inserting a cached orderbook, get_orderbook returns it."""
        svc = _make_service()
        ob = _make_orderbook(
            "binance", "BTC/USDT",
            bids=[(60_000, 1.0), (59_990, 2.0)],
            asks=[(60_010, 1.0), (60_020, 2.0)],
        )

        svc._orderbooks[("binance", "BTC/USDT")] = CachedOrderbook(
            orderbook=ob, received_at=time.time(),
        )

        result = svc.get_orderbook("binance", "BTC/USDT")
        assert result is not None
        assert result.best_bid == 60_000
        assert result.best_ask == 60_010
        assert len(result.bids) == 2
        assert len(result.asks) == 2

    def test_get_orderbook_returns_none_for_missing(self):
        svc = _make_service()
        result = svc.get_orderbook("nonexistent", "BTC/USDT")
        assert result is None


# =====================================================================
# Data freshness
# =====================================================================

class TestDataFreshness:

    def test_new_data_not_stale(self):
        """Data just received should not be stale."""
        svc = _make_service()
        svc._stale_threshold_s = 5.0

        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", 60_000, 60_010),
            received_at=time.time(),  # just now
        )

        assert svc.is_data_stale("binance", "BTC/USDT") is False

    def test_old_data_is_stale(self):
        """Data received 10 seconds ago should be stale (threshold=5s)."""
        svc = _make_service()
        svc._stale_threshold_s = 5.0

        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", 60_000, 60_010),
            received_at=time.time() - 10.0,  # 10 seconds ago
        )

        assert svc.is_data_stale("binance", "BTC/USDT") is True

    def test_missing_data_is_stale(self):
        """No data at all for a key is considered stale."""
        svc = _make_service()
        assert svc.is_data_stale("binance", "BTC/USDT") is True

    def test_get_data_age_returns_seconds(self):
        """get_data_age returns the age in seconds."""
        svc = _make_service()
        received_at = time.time() - 3.0

        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", 60_000, 60_010),
            received_at=received_at,
        )

        age = svc.get_data_age("binance", "BTC/USDT")
        assert age is not None
        assert age >= 3.0
        assert age < 5.0  # should not take 2s to run this test

    def test_get_data_age_none_for_missing(self):
        svc = _make_service()
        assert svc.get_data_age("binance", "BTC/USDT") is None

    def test_stale_threshold_setter(self):
        """Stale threshold can be updated, with a minimum of 0.1."""
        svc = _make_service()
        svc.stale_threshold_s = 10.0
        assert svc.stale_threshold_s == 10.0

        svc.stale_threshold_s = 0.01  # below minimum
        assert svc.stale_threshold_s == 0.1


# =====================================================================
# Cross-exchange spread
# =====================================================================

class TestGetSpread:

    def test_get_spread_finds_best_across_exchanges(self):
        """With 2 exchanges, get_spread finds the best bid and best ask."""
        svc = _make_service()
        svc._stale_threshold_s = 5.0
        now = time.time()

        # Binance: bid=60000, ask=60010
        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", bid=60_000, ask=60_010),
            received_at=now,
        )
        # OKX: bid=60050, ask=60060
        svc._tickers[("okx", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("okx", "BTC/USDT", bid=60_050, ask=60_060),
            received_at=now,
        )

        spread = svc.get_spread("BTC/USDT")
        assert spread is not None
        assert isinstance(spread, SpreadInfo)

        # Best bid = 60050 (OKX), best ask = 60010 (Binance)
        assert spread.best_bid == 60_050
        assert spread.best_bid_exchange == "okx"
        assert spread.best_ask == 60_010
        assert spread.best_ask_exchange == "binance"

        # Spread = (60050 - 60010) / 60010 * 100 = ~0.0666%
        expected_spread_pct = (60_050 - 60_010) / 60_010 * 100.0
        assert spread.spread_pct == pytest.approx(expected_spread_pct)

    def test_get_spread_none_with_single_exchange(self):
        """Need at least 2 exchanges for a spread."""
        svc = _make_service()
        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", 60_000, 60_010),
            received_at=time.time(),
        )

        spread = svc.get_spread("BTC/USDT")
        assert spread is None

    def test_get_spread_none_with_no_data(self):
        svc = _make_service()
        spread = svc.get_spread("BTC/USDT")
        assert spread is None

    def test_get_spread_ignores_stale_data(self):
        """Stale data should be excluded from spread calculation."""
        svc = _make_service()
        svc._stale_threshold_s = 5.0
        now = time.time()

        # Fresh data from binance
        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", 60_000, 60_010),
            received_at=now,
        )
        # Stale data from OKX (10 seconds old)
        svc._tickers[("okx", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("okx", "BTC/USDT", 60_050, 60_060),
            received_at=now - 10.0,
        )

        spread = svc.get_spread("BTC/USDT")
        # Only 1 fresh exchange -> None
        assert spread is None

    def test_get_spread_negative_when_no_arb(self):
        """When best bid < best ask across exchanges, spread is negative."""
        svc = _make_service()
        now = time.time()

        # Both exchanges: ask > bid, no cross-exchange arb
        svc._tickers[("binance", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("binance", "BTC/USDT", bid=59_990, ask=60_010),
            received_at=now,
        )
        svc._tickers[("okx", "BTC/USDT")] = CachedTicker(
            ticker=_make_ticker("okx", "BTC/USDT", bid=59_995, ask=60_005),
            received_at=now,
        )

        spread = svc.get_spread("BTC/USDT")
        assert spread is not None
        # Best bid=59995 (okx), best ask=60005 (okx)
        # Spread = (59995 - 60005) / 60005 * 100 = negative
        assert spread.spread_pct < 0


# =====================================================================
# WS callback integration
# =====================================================================

class TestWSCallbacks:

    @pytest.mark.asyncio
    async def test_on_ws_ticker_populates_cache(self):
        """_on_ws_ticker should store the ticker in the cache."""
        svc = _make_service()
        ticker = _make_ticker("binance", "BTC/USDT", 60_000, 60_010)

        await svc._on_ws_ticker(ticker)

        cached = svc.get_ticker("binance", "BTC/USDT")
        assert cached is not None
        assert cached.bid == 60_000
        assert cached.ask == 60_010

    @pytest.mark.asyncio
    async def test_on_ws_orderbook_populates_cache(self):
        """_on_ws_orderbook should store the orderbook in the cache."""
        svc = _make_service()
        ob = _make_orderbook(
            "binance", "BTC/USDT",
            bids=[(60_000, 1.0)],
            asks=[(60_010, 1.0)],
        )

        await svc._on_ws_orderbook(ob)

        cached = svc.get_orderbook("binance", "BTC/USDT")
        assert cached is not None
        assert cached.best_bid == 60_000
        assert cached.best_ask == 60_010


# =====================================================================
# CachedTicker / CachedOrderbook data classes
# =====================================================================

class TestCacheWrappers:

    def test_cached_ticker_age(self):
        """age_seconds should increase over time."""
        ticker = _make_ticker("binance", "BTC/USDT", 60_000, 60_010)
        cached = CachedTicker(ticker=ticker, received_at=time.time() - 2.0)
        assert cached.age_seconds >= 2.0
        assert cached.age_seconds < 4.0

    def test_cached_orderbook_age(self):
        ob = _make_orderbook("binance", "BTC/USDT", [(60_000, 1)], [(60_010, 1)])
        cached = CachedOrderbook(orderbook=ob, received_at=time.time() - 3.0)
        assert cached.age_seconds >= 3.0
        assert cached.age_seconds < 5.0
