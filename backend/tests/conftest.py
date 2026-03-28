"""
Shared fixtures for the arbitrage backend test suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.events import EventBus
from app.exchanges.base import OrderbookLevel, StandardOrderbook, StandardTicker
from app.exchanges.mock import MockExchangeAdapter


# ---------------------------------------------------------------------------
# Settings override
# ---------------------------------------------------------------------------

@pytest.fixture
def test_settings() -> Settings:
    """Return a Settings instance with safe defaults for testing."""
    return Settings(
        debug=True,
        trading={"paper_mode": True, "enabled_exchanges": ["mock_binance", "mock_okx"]},
        risk={
            "max_order_value_usdt": 10_000.0,
            "max_position_value_usdt": 50_000.0,
            "max_daily_loss_usdt": 500.0,
            "max_consecutive_failures": 5,
            "max_slippage_pct": 0.15,
            "min_profit_threshold_pct": 0.05,
            "min_profit_threshold_usdt": 1.0,
            "max_open_orders": 10,
        },
        strategy={
            "enabled_pairs": ["BTC/USDT", "ETH/USDT"],
            "scan_interval_ms": 500,
            "min_depth_usdt": 500.0,
            "orderbook_depth_levels": 10,
        },
    )


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus() -> EventBus:
    """Fresh event bus for each test."""
    return EventBus()


# ---------------------------------------------------------------------------
# Mock exchange adapters with known offsets
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_exchange_a() -> MockExchangeAdapter:
    """MockExchangeAdapter with name='mock_binance', offset=0 (baseline prices)."""
    MockExchangeAdapter.reset_shared_prices()
    adapter = MockExchangeAdapter(
        name="mock_binance",
        price_offset_pct=0.0,
        initial_balances={"BTC": 1.0, "ETH": 10.0, "USDT": 100_000.0, "SOL": 50.0},
        taker_fee=0.001,
        maker_fee=0.001,
    )
    return adapter


@pytest.fixture
def mock_exchange_b() -> MockExchangeAdapter:
    """MockExchangeAdapter with name='mock_okx', offset=0.3% higher prices."""
    adapter = MockExchangeAdapter(
        name="mock_okx",
        price_offset_pct=0.3,
        initial_balances={"BTC": 1.0, "ETH": 10.0, "USDT": 100_000.0, "SOL": 50.0},
        taker_fee=0.001,
        maker_fee=0.001,
    )
    return adapter


# ---------------------------------------------------------------------------
# Sample orderbook data for deterministic testing
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_orderbook_asks() -> list[tuple[float, float]]:
    """Known ask levels: (price, quantity).

    Sorted ascending by price (cheapest first).
    Total depth: 1 + 2 + 3 + 2 + 1 = 9 units.
    """
    return [
        (100.0, 1.0),
        (101.0, 2.0),
        (102.0, 3.0),
        (103.0, 2.0),
        (104.0, 1.0),
    ]


@pytest.fixture
def sample_orderbook_bids() -> list[tuple[float, float]]:
    """Known bid levels: (price, quantity).

    Sorted descending by price (highest first).
    Total depth: 3 + 2 + 2 + 1 + 1 = 9 units.
    """
    return [
        (100.0, 3.0),
        (99.0, 2.0),
        (98.0, 2.0),
        (97.0, 1.0),
        (96.0, 1.0),
    ]


# ---------------------------------------------------------------------------
# Mock exchange factory
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_exchange_factory():
    """Return a lightweight fake ExchangeFactory backed by MockExchangeAdapters.

    The factory exposes ``.get()`` and ``.get_all()`` just like the real one.
    """

    class _FakeFactory:
        def __init__(self) -> None:
            self._adapters: dict[str, MockExchangeAdapter] = {}

        def add(self, name: str, adapter: MockExchangeAdapter) -> None:
            self._adapters[name] = adapter

        def get(self, name: str):
            return self._adapters.get(name)

        def get_all(self) -> dict[str, MockExchangeAdapter]:
            return dict(self._adapters)

    return _FakeFactory()


# ---------------------------------------------------------------------------
# Helpers for building StandardOrderbook from tuples
# ---------------------------------------------------------------------------

def make_orderbook(
    exchange: str,
    symbol: str,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> StandardOrderbook:
    """Build a StandardOrderbook from (price, qty) tuple lists."""
    return StandardOrderbook(
        exchange=exchange,
        symbol=symbol,
        bids=[OrderbookLevel(price=p, quantity=q) for p, q in bids],
        asks=[OrderbookLevel(price=p, quantity=q) for p, q in asks],
    )


def make_ticker(
    exchange: str,
    symbol: str,
    bid: float,
    ask: float,
) -> StandardTicker:
    """Build a StandardTicker with the given bid/ask."""
    return StandardTicker(
        exchange=exchange,
        symbol=symbol,
        bid=bid,
        ask=ask,
        bid_size=1.0,
        ask_size=1.0,
        last_price=(bid + ask) / 2.0,
        volume_24h=10000.0,
    )
