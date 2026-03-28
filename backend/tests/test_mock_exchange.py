"""Tests for MockExchangeAdapter -- verifying realistic market simulation."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.exchanges.base import (
    OrderSide,
    OrderStatus,
    OrderType,
    StandardBalance,
)
from app.exchanges.mock import MockExchangeAdapter


@pytest.fixture(autouse=True)
def reset_shared_prices():
    """Reset class-level shared prices before each test to avoid cross-test pollution."""
    MockExchangeAdapter.reset_shared_prices()
    yield
    MockExchangeAdapter.reset_shared_prices()


@pytest_asyncio.fixture
async def exchange_a() -> MockExchangeAdapter:
    """Initialized mock exchange with 0% offset (baseline)."""
    adapter = MockExchangeAdapter(
        name="mock_binance",
        price_offset_pct=0.0,
        initial_balances={"BTC": 1.0, "ETH": 10.0, "USDT": 100_000.0},
        taker_fee=0.001,
        maker_fee=0.001,
    )
    await adapter.initialize()
    yield adapter
    await adapter.shutdown()


@pytest_asyncio.fixture
async def exchange_b() -> MockExchangeAdapter:
    """Initialized mock exchange with 0.5% higher prices."""
    adapter = MockExchangeAdapter(
        name="mock_okx",
        price_offset_pct=0.5,
        initial_balances={"BTC": 1.0, "ETH": 10.0, "USDT": 100_000.0},
        taker_fee=0.001,
        maker_fee=0.001,
    )
    await adapter.initialize()
    yield adapter
    await adapter.shutdown()


# =====================================================================
# Lifecycle
# =====================================================================

class TestLifecycle:

    @pytest.mark.asyncio
    async def test_initialize_sets_up_state(self):
        adapter = MockExchangeAdapter(name="init_test")
        assert adapter._initialized is False
        await adapter.initialize()
        assert adapter._initialized is True
        assert len(adapter._prices) > 0
        assert "BTC/USDT" in adapter._prices
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_initialized(self, exchange_a: MockExchangeAdapter):
        info = await exchange_a.get_exchange_info()
        assert info.is_connected is True
        assert info.name == "mock_binance"
        assert info.server_time is not None


# =====================================================================
# Market data
# =====================================================================

class TestMarketData:

    @pytest.mark.asyncio
    async def test_get_symbols_returns_configured_pairs(self, exchange_a: MockExchangeAdapter):
        symbols = await exchange_a.get_symbols()
        symbol_names = [s.symbol for s in symbols]
        assert "BTC/USDT" in symbol_names
        assert "ETH/USDT" in symbol_names
        assert "SOL/USDT" in symbol_names
        assert len(symbols) >= 5

        # Verify symbol metadata
        btc_sym = next(s for s in symbols if s.symbol == "BTC/USDT")
        assert btc_sym.base_asset == "BTC"
        assert btc_sym.quote_asset == "USDT"
        assert btc_sym.is_active is True
        assert btc_sym.step_size > 0
        assert btc_sym.min_quantity > 0

    @pytest.mark.asyncio
    async def test_get_ticker_has_valid_spread(self, exchange_a: MockExchangeAdapter):
        ticker = await exchange_a.get_ticker("BTC/USDT")
        assert ticker.bid > 0
        assert ticker.ask > 0
        assert ticker.bid < ticker.ask  # bid always below ask
        assert ticker.exchange == "mock_binance"
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last_price > 0
        assert ticker.volume_24h > 0

    @pytest.mark.asyncio
    async def test_get_ticker_price_offset(self, exchange_a: MockExchangeAdapter, exchange_b: MockExchangeAdapter):
        """Two mocks with different offsets should have consistently different mid-prices."""
        spread_sum = 0.0
        n = 20
        for _ in range(n):
            ta = await exchange_a.get_ticker("BTC/USDT")
            tb = await exchange_b.get_ticker("BTC/USDT")
            mid_a = (ta.bid + ta.ask) / 2
            mid_b = (tb.bid + tb.ask) / 2
            spread_sum += (mid_b - mid_a)

        avg_spread = spread_sum / n
        # Exchange B has +0.5% offset on ~60000 -> ~300 USDT spread
        assert avg_spread > 0, f"Expected positive average spread, got {avg_spread}"

    @pytest.mark.asyncio
    async def test_get_orderbook_structure(self, exchange_a: MockExchangeAdapter):
        ob = await exchange_a.get_orderbook("BTC/USDT", depth=10)
        assert ob.exchange == "mock_binance"
        assert ob.symbol == "BTC/USDT"
        assert len(ob.bids) == 10
        assert len(ob.asks) == 10
        # All levels should have positive price and quantity
        for level in ob.bids + ob.asks:
            assert level.price > 0
            assert level.quantity > 0

    @pytest.mark.asyncio
    async def test_get_orderbook_bids_descending(self, exchange_a: MockExchangeAdapter):
        ob = await exchange_a.get_orderbook("BTC/USDT", depth=10)
        bid_prices = [level.price for level in ob.bids]
        for i in range(len(bid_prices) - 1):
            assert bid_prices[i] >= bid_prices[i + 1], \
                f"Bids not descending at index {i}: {bid_prices[i]} < {bid_prices[i + 1]}"

    @pytest.mark.asyncio
    async def test_get_orderbook_asks_ascending(self, exchange_a: MockExchangeAdapter):
        ob = await exchange_a.get_orderbook("BTC/USDT", depth=10)
        ask_prices = [level.price for level in ob.asks]
        for i in range(len(ask_prices) - 1):
            assert ask_prices[i] <= ask_prices[i + 1], \
                f"Asks not ascending at index {i}: {ask_prices[i]} > {ask_prices[i + 1]}"

    @pytest.mark.asyncio
    async def test_get_orderbook_depth_parameter(self, exchange_a: MockExchangeAdapter):
        ob5 = await exchange_a.get_orderbook("BTC/USDT", depth=5)
        ob20 = await exchange_a.get_orderbook("BTC/USDT", depth=20)
        assert len(ob5.bids) == 5
        assert len(ob5.asks) == 5
        assert len(ob20.bids) == 20
        assert len(ob20.asks) == 20

    @pytest.mark.asyncio
    async def test_get_orderbook_best_bid_below_best_ask(self, exchange_a: MockExchangeAdapter):
        ob = await exchange_a.get_orderbook("BTC/USDT", depth=10)
        assert ob.best_bid < ob.best_ask
        assert ob.spread > 0
        assert ob.mid_price > 0


# =====================================================================
# Account
# =====================================================================

class TestAccount:

    @pytest.mark.asyncio
    async def test_get_balance_has_standard_assets(self, exchange_a: MockExchangeAdapter):
        balances = await exchange_a.get_balance()
        assert "USDT" in balances
        assert "BTC" in balances
        assert "ETH" in balances

    @pytest.mark.asyncio
    async def test_get_balance_values_positive(self, exchange_a: MockExchangeAdapter):
        balances = await exchange_a.get_balance()
        assert balances["USDT"].free == 100_000.0
        assert balances["BTC"].free == 1.0
        assert balances["ETH"].free == 10.0
        for bal in balances.values():
            assert bal.locked == 0.0

    @pytest.mark.asyncio
    async def test_get_fees(self, exchange_a: MockExchangeAdapter):
        fees = await exchange_a.get_fees("BTC/USDT")
        assert fees["maker"] == 0.001
        assert fees["taker"] == 0.001


# =====================================================================
# Trading
# =====================================================================

class TestTrading:

    @pytest.mark.asyncio
    async def test_place_market_buy_order_fills_immediately(self, exchange_a: MockExchangeAdapter):
        order = await exchange_a.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 0.01
        assert order.avg_fill_price is not None
        assert order.avg_fill_price > 0
        assert order.fee > 0
        assert order.fee_asset == "USDT"

    @pytest.mark.asyncio
    async def test_place_market_sell_order_fills_immediately(self, exchange_a: MockExchangeAdapter):
        order = await exchange_a.place_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 0.01
        assert order.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_place_order_updates_balance(self, exchange_a: MockExchangeAdapter):
        bal_before = await exchange_a.get_balance()
        btc_before = bal_before["BTC"].free

        order = await exchange_a.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )

        bal_after = await exchange_a.get_balance()
        btc_after = bal_after["BTC"].free

        # BTC should increase by 0.01
        assert btc_after == pytest.approx(btc_before + 0.01)

        # USDT should decrease
        usdt_before = bal_before["USDT"].free
        usdt_after = bal_after["USDT"].free + bal_after["USDT"].locked
        assert usdt_after < usdt_before

    @pytest.mark.asyncio
    async def test_place_order_deducts_fee(self, exchange_a: MockExchangeAdapter):
        order = await exchange_a.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        # Fee = quantity * fill_price * taker_fee_rate
        expected_fee = 0.1 * order.avg_fill_price * 0.001
        assert order.fee == pytest.approx(expected_fee, rel=0.2)

    @pytest.mark.asyncio
    async def test_get_order_status_after_fill(self, exchange_a: MockExchangeAdapter):
        order = await exchange_a.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        status = await exchange_a.get_order_status("BTC/USDT", order.order_id)
        assert status.status == OrderStatus.FILLED
        assert status.order_id == order.order_id

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order_returns_false(self, exchange_a: MockExchangeAdapter):
        result = await exchange_a.cancel_order("BTC/USDT", "nonexistent_order_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_open_limit_order(self, exchange_a: MockExchangeAdapter):
        order = await exchange_a.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=30_000.0,  # far below market
        )
        cancelled = await exchange_a.cancel_order("BTC/USDT", order.order_id)
        assert cancelled is True

        status = await exchange_a.get_order_status("BTC/USDT", order.order_id)
        assert status.status == OrderStatus.CANCELED


# =====================================================================
# Cross-exchange spread verification (critical)
# =====================================================================

class TestCrossExchangeSpread:

    @pytest.mark.asyncio
    async def test_two_exchanges_create_spread(
        self, exchange_a: MockExchangeAdapter, exchange_b: MockExchangeAdapter
    ):
        """Mock exchanges with different offsets create an exploitable spread.

        Exchange A: offset 0% -> baseline prices
        Exchange B: offset +0.5% -> higher prices

        Strategy: buy on A (cheaper), sell on B (more expensive).
        The B bid should on average exceed the A ask.
        """
        spread_sum = 0.0
        n = 20
        for _ in range(n):
            ta = await exchange_a.get_ticker("BTC/USDT")
            tb = await exchange_b.get_ticker("BTC/USDT")
            spread_sum += (tb.bid - ta.ask)

        avg_spread = spread_sum / n
        # With 0.5% offset on ~60000, expected spread ~ 300 USDT minus intra-exchange spread
        assert avg_spread > 0, f"Expected positive average cross-exchange spread, got {avg_spread}"

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        adapter = MockExchangeAdapter(
            name="reset_test",
            initial_balances={"BTC": 5.0, "USDT": 50_000.0},
        )
        await adapter.initialize()

        # Place an order
        await adapter.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        assert len(adapter._orders) > 0

        # Reset
        adapter.reset(initial_balances={"BTC": 1.0, "USDT": 100_000.0})
        assert len(adapter._orders) == 0

        balances = await adapter.get_balance()
        assert balances["BTC"].free == 1.0
        assert balances["USDT"].free == 100_000.0

        await adapter.shutdown()
