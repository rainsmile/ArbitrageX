"""Tests for SimulationService -- orderbook-based trade simulation.

Tests the single-order simulation, cross-exchange simulation,
triangular simulation, slippage models, and fee models.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exchanges.base import OrderbookLevel, StandardOrderbook, StandardTicker
from app.services.scanner import OpportunityCandidate
from app.services.simulation import (
    DepthBasedSlippageModel,
    FixedSlippageModel,
    SimulatedFill,
    SimulationResult,
    SimulationService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orderbook(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    exchange: str = "test_ex",
    symbol: str = "BTC/USDT",
) -> StandardOrderbook:
    """Create an orderbook from (price, qty) tuples."""
    return StandardOrderbook(
        exchange=exchange,
        symbol=symbol,
        bids=[OrderbookLevel(price=p, quantity=q) for p, q in bids],
        asks=[OrderbookLevel(price=p, quantity=q) for p, q in asks],
    )


def _make_ticker(
    exchange: str, symbol: str, bid: float, ask: float,
) -> StandardTicker:
    return StandardTicker(
        exchange=exchange, symbol=symbol, bid=bid, ask=ask,
        bid_size=1.0, ask_size=1.0, last_price=(bid + ask) / 2.0,
    )


def _make_simulation_service(
    orderbooks: dict[tuple[str, str], StandardOrderbook] | None = None,
    tickers: dict[tuple[str, str], StandardTicker] | None = None,
) -> SimulationService:
    """Build a SimulationService with mock MarketDataService."""
    market_data = MagicMock()
    market_data.get_orderbook.side_effect = lambda exch, sym: (
        (orderbooks or {}).get((exch, sym))
    )
    market_data.get_ticker.side_effect = lambda exch, sym: (
        (tickers or {}).get((exch, sym))
    )

    factory = MagicMock()
    svc = SimulationService(market_data=market_data, exchange_factory=factory)
    svc.slippage_mode = "depth"
    return svc


# =====================================================================
# DepthBasedSlippageModel
# =====================================================================

class TestDepthBasedSlippageModel:

    def test_walk_single_level(self):
        model = DepthBasedSlippageModel()
        levels = [OrderbookLevel(price=100.0, quantity=5.0)]
        avg_price, filled_qty, consumed = model.walk_book(levels, quantity=3.0)

        assert filled_qty == 3.0
        assert avg_price == 100.0
        assert consumed == 1

    def test_walk_multiple_levels(self):
        model = DepthBasedSlippageModel()
        levels = [
            OrderbookLevel(price=100.0, quantity=1.0),
            OrderbookLevel(price=101.0, quantity=1.0),
            OrderbookLevel(price=102.0, quantity=1.0),
        ]
        avg_price, filled_qty, consumed = model.walk_book(levels, quantity=3.0)

        assert filled_qty == 3.0
        expected_avg = (100.0 + 101.0 + 102.0) / 3.0
        assert avg_price == pytest.approx(expected_avg)
        assert consumed == 3

    def test_partial_fill(self):
        model = DepthBasedSlippageModel()
        levels = [
            OrderbookLevel(price=100.0, quantity=1.0),
            OrderbookLevel(price=101.0, quantity=0.5),
        ]
        avg_price, filled_qty, consumed = model.walk_book(levels, quantity=5.0)

        assert filled_qty == 1.5
        expected_avg = (100.0 * 1.0 + 101.0 * 0.5) / 1.5
        assert avg_price == pytest.approx(expected_avg)
        assert consumed == 2

    def test_empty_book(self):
        model = DepthBasedSlippageModel()
        avg_price, filled_qty, consumed = model.walk_book([], quantity=1.0)

        assert filled_qty == 0.0
        assert avg_price == 0.0
        assert consumed == 0


# =====================================================================
# FixedSlippageModel
# =====================================================================

class TestFixedSlippageModel:

    def test_buy_increases_price(self):
        model = FixedSlippageModel(slippage_pct=0.05)
        adjusted = model.apply(price=60_000.0, side="BUY")
        # 60000 * 1.0005 = 60030
        assert adjusted == pytest.approx(60_030.0)

    def test_sell_decreases_price(self):
        model = FixedSlippageModel(slippage_pct=0.05)
        adjusted = model.apply(price=60_000.0, side="SELL")
        # 60000 * 0.9995 = 59970
        assert adjusted == pytest.approx(59_970.0)

    def test_zero_slippage(self):
        model = FixedSlippageModel(slippage_pct=0.0)
        assert model.apply(100.0, "BUY") == 100.0
        assert model.apply(100.0, "SELL") == 100.0


# =====================================================================
# SimulationService.simulate_order -- BUY side
# =====================================================================

class TestSimulateOrderBuy:

    def test_buy_walks_asks(self):
        """Known asks: [(100, 1), (101, 2), (102, 3)].
        Buy 2.0 units: 1@100 + 1@101 = avg 100.5.
        """
        ob = _make_orderbook(
            bids=[(99, 5.0)],
            asks=[(100, 1.0), (101, 2.0), (102, 3.0)],
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=99, ask=100)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=2.0,
            orderbook=ob,
        )

        assert fill.fill_quantity == 2.0
        # 1@100 + 1@101 = 201 / 2 = 100.5
        assert fill.fill_price == pytest.approx(100.5)
        assert fill.levels_consumed == 2
        assert fill.partial is False

    def test_buy_fee_deduction(self):
        """Verify fee is correctly calculated as fee_pct% of notional."""
        ob = _make_orderbook(
            bids=[(99, 5.0)],
            asks=[(100, 10.0)],
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=99, ask=100)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=1.0,
            orderbook=ob,
        )

        # Notional = 100 * 1 = 100
        assert fill.notional_value == pytest.approx(100.0)
        # Fee = notional * (fee_pct / 100)
        expected_fee = 100.0 * (fill.fee_pct / 100.0)
        assert fill.fee_usdt == pytest.approx(expected_fee)
        assert fill.fee_pct > 0

    def test_buy_slippage_relative_to_top(self):
        """Slippage should be (avg_price - top_ask) / top_ask * 100."""
        ob = _make_orderbook(
            bids=[(99, 5.0)],
            asks=[(100, 1.0), (110, 1.0)],  # big jump at second level
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=99, ask=100)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=2.0,
            orderbook=ob,
        )

        # avg = (100 + 110) / 2 = 105, top = 100
        # slippage = (105 - 100) / 100 * 100 = 5%
        assert fill.fill_price == pytest.approx(105.0)
        assert fill.slippage_pct == pytest.approx(5.0)


# =====================================================================
# SimulationService.simulate_order -- SELL side
# =====================================================================

class TestSimulateOrderSell:

    def test_sell_walks_bids(self):
        """Known bids: [(100, 3), (99, 2), (98, 1)].
        Sell 4.0 units: 3@100 + 1@99 = avg 99.75.
        """
        ob = _make_orderbook(
            bids=[(100, 3.0), (99, 2.0), (98, 1.0)],
            asks=[(101, 5.0)],
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=100, ask=101)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="SELL",
            quantity=4.0,
            orderbook=ob,
        )

        assert fill.fill_quantity == 4.0
        # 3@100 + 1@99 = 300 + 99 = 399 / 4 = 99.75
        assert fill.fill_price == pytest.approx(99.75)
        assert fill.levels_consumed == 2
        assert fill.partial is False

    def test_sell_slippage(self):
        """Sell slippage = (top_bid - avg_fill) / top_bid * 100."""
        ob = _make_orderbook(
            bids=[(100, 1.0), (90, 1.0)],  # big gap
            asks=[(101, 5.0)],
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=100, ask=101)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="SELL",
            quantity=2.0,
            orderbook=ob,
        )

        # avg = (100 + 90) / 2 = 95, top = 100
        # slippage = (100 - 95) / 100 * 100 = 5%
        assert fill.fill_price == pytest.approx(95.0)
        assert fill.slippage_pct == pytest.approx(5.0)


# =====================================================================
# Partial fills
# =====================================================================

class TestSimulateOrderPartialFill:

    def test_partial_fill_depth_insufficient(self):
        """Orderbook has only 2 units, try to buy 5."""
        ob = _make_orderbook(
            bids=[(99, 5.0)],
            asks=[(100, 1.0), (101, 1.0)],  # only 2 units
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=99, ask=100)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=5.0,
            orderbook=ob,
        )

        assert fill.fill_quantity == pytest.approx(2.0)
        assert fill.partial is True

    def test_zero_fill_on_empty_asks(self):
        """Empty ask book -> zero fill."""
        ob = _make_orderbook(
            bids=[(99, 5.0)],
            asks=[],
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=99, ask=100)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=1.0,
            orderbook=ob,
        )

        assert fill.fill_quantity == 0.0
        assert fill.partial is True


# =====================================================================
# Cross-exchange simulation
# =====================================================================

class TestSimulateCrossExchange:

    @pytest.mark.asyncio
    async def test_simulate_cross_exchange_profitable(self):
        """Buy exchange has low asks, sell exchange has high bids."""
        buy_ob = _make_orderbook(
            bids=[(59_900, 1.0)],
            asks=[(60_000, 1.0), (60_010, 1.0)],
            exchange="buy_ex",
        )
        sell_ob = _make_orderbook(
            bids=[(60_500, 1.0), (60_490, 1.0)],
            asks=[(60_600, 1.0)],
            exchange="sell_ex",
        )

        buy_ticker = _make_ticker("buy_ex", "BTC/USDT", bid=59_900, ask=60_000)
        sell_ticker = _make_ticker("sell_ex", "BTC/USDT", bid=60_500, ask=60_600)

        svc = _make_simulation_service(
            orderbooks={
                ("buy_ex", "BTC/USDT"): buy_ob,
                ("sell_ex", "BTC/USDT"): sell_ob,
            },
            tickers={
                ("buy_ex", "BTC/USDT"): buy_ticker,
                ("sell_ex", "BTC/USDT"): sell_ticker,
            },
        )

        opp = OpportunityCandidate(
            strategy_type="CROSS_EXCHANGE",
            symbol="BTC/USDT",
            symbols=["BTC/USDT"],
            exchanges=["buy_ex", "sell_ex"],
            buy_exchange="buy_ex",
            sell_exchange="sell_ex",
            buy_price=60_000,
            sell_price=60_500,
            executable_quantity=0.5,
        )

        result = await svc.simulate_cross_exchange(opp)

        assert result.strategy_type == "CROSS_EXCHANGE"
        assert result.gross_profit_usdt > 0
        # Entry at ~60000, exit at ~60500, gross ~ 250 for 0.5 units
        assert result.gross_profit_usdt == pytest.approx(250.0, rel=0.01)
        assert result.total_fees_usdt > 0
        assert result.net_profit_usdt > 0
        assert result.feasible is True
        assert len(result.legs) == 2
        assert result.legs[0].side == "BUY"
        assert result.legs[1].side == "SELL"

    @pytest.mark.asyncio
    async def test_simulate_cross_exchange_unprofitable(self):
        """Tight spread eaten by fees -> negative net profit."""
        buy_ob = _make_orderbook(
            bids=[(59_990, 1.0)],
            asks=[(60_000, 1.0)],
            exchange="buy_ex",
        )
        sell_ob = _make_orderbook(
            bids=[(60_010, 1.0)],
            asks=[(60_020, 1.0)],
            exchange="sell_ex",
        )

        buy_ticker = _make_ticker("buy_ex", "BTC/USDT", bid=59_990, ask=60_000)
        sell_ticker = _make_ticker("sell_ex", "BTC/USDT", bid=60_010, ask=60_020)

        svc = _make_simulation_service(
            orderbooks={
                ("buy_ex", "BTC/USDT"): buy_ob,
                ("sell_ex", "BTC/USDT"): sell_ob,
            },
            tickers={
                ("buy_ex", "BTC/USDT"): buy_ticker,
                ("sell_ex", "BTC/USDT"): sell_ticker,
            },
        )

        opp = OpportunityCandidate(
            strategy_type="CROSS_EXCHANGE",
            symbol="BTC/USDT",
            symbols=["BTC/USDT"],
            buy_exchange="buy_ex",
            sell_exchange="sell_ex",
            executable_quantity=0.5,
        )

        result = await svc.simulate_cross_exchange(opp)

        # Gross: 0.5 * (60010 - 60000) = 5 USDT
        # Fees: ~0.1% * 60000 * 0.5 * 2 ~ 60 USDT
        # Net is deeply negative
        assert result.net_profit_usdt < 0
        assert result.feasible is False

    @pytest.mark.asyncio
    async def test_simulate_cross_exchange_zero_quantity(self):
        """Zero executable quantity -> infeasible."""
        svc = _make_simulation_service()

        opp = OpportunityCandidate(
            strategy_type="CROSS_EXCHANGE",
            symbol="BTC/USDT",
            symbols=["BTC/USDT"],
            buy_exchange="buy_ex",
            sell_exchange="sell_ex",
            executable_quantity=0.0,
        )

        result = await svc.simulate_cross_exchange(opp)
        assert result.feasible is False
        assert "Zero" in result.reason


# =====================================================================
# Fee model tests
# =====================================================================

class TestFeeModel:

    def test_fee_correctly_deducted(self):
        """Verify fees = notional * (fee_pct / 100)."""
        ob = _make_orderbook(
            bids=[(59_990, 10.0)],
            asks=[(60_000, 10.0)],
        )
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=59_990, ask=60_000)

        svc = _make_simulation_service(
            orderbooks={("test_ex", "BTC/USDT"): ob},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=1.0,
            orderbook=ob,
        )

        notional = fill.fill_price * fill.fill_quantity
        assert fill.notional_value == pytest.approx(notional)
        expected_fee = notional * (fill.fee_pct / 100.0)
        assert fill.fee_usdt == pytest.approx(expected_fee)

    def test_fee_pct_from_exchange_table(self):
        """Different exchanges have different default fees."""
        ob = _make_orderbook(bids=[(100, 10)], asks=[(101, 10)])
        ticker_bn = _make_ticker("binance", "BTC/USDT", bid=100, ask=101)
        ticker_okx = _make_ticker("okx", "BTC/USDT", bid=100, ask=101)

        svc = _make_simulation_service(
            orderbooks={
                ("binance", "BTC/USDT"): ob,
                ("okx", "BTC/USDT"): ob,
            },
            tickers={
                ("binance", "BTC/USDT"): ticker_bn,
                ("okx", "BTC/USDT"): ticker_okx,
            },
        )

        fill_bn = svc.simulate_order("binance", "BTC/USDT", "BUY", 1.0, orderbook=ob)
        fill_okx = svc.simulate_order("okx", "BTC/USDT", "BUY", 1.0, orderbook=ob)

        assert fill_bn.fee_pct == pytest.approx(0.10)  # binance taker = 0.10%
        assert fill_okx.fee_pct == pytest.approx(0.10)  # okx taker = 0.10%


# =====================================================================
# Fixed slippage mode fallback
# =====================================================================

class TestFixedSlippageMode:

    def test_fixed_mode_when_no_orderbook(self):
        """When no orderbook is available, falls back to fixed slippage."""
        ticker = _make_ticker("test_ex", "BTC/USDT", bid=59_990, ask=60_000)

        svc = _make_simulation_service(
            orderbooks={},
            tickers={("test_ex", "BTC/USDT"): ticker},
        )
        svc.slippage_mode = "fixed"

        fill = svc.simulate_order(
            exchange="test_ex",
            symbol="BTC/USDT",
            side="BUY",
            quantity=1.0,
        )

        # Fixed slippage: price * (1 + 0.05/100) = 60000 * 1.0005 = 60030
        assert fill.fill_price == pytest.approx(60_030.0)
        assert fill.fill_quantity == 1.0
        assert fill.partial is False


# =====================================================================
# Triangular simulation
# =====================================================================

class TestSimulateTriangular:

    @pytest.mark.asyncio
    async def test_simulate_triangular_basic(self):
        """Set up 3 pairs with known prices and simulate the path."""
        exchange = "test_ex"

        # BTC/USDT, ETH/BTC, ETH/USDT
        ob_btc = _make_orderbook(
            bids=[(59_990, 10.0)],
            asks=[(60_000, 10.0)],
            exchange=exchange, symbol="BTC/USDT",
        )
        ob_ethbtc = _make_orderbook(
            bids=[(0.058, 100.0)],
            asks=[(0.0581, 100.0)],
            exchange=exchange, symbol="ETH/BTC",
        )
        ob_eth = _make_orderbook(
            bids=[(3_500, 10.0)],
            asks=[(3_510, 10.0)],
            exchange=exchange, symbol="ETH/USDT",
        )

        ticker_btc = _make_ticker(exchange, "BTC/USDT", bid=59_990, ask=60_000)
        ticker_ethbtc = _make_ticker(exchange, "ETH/BTC", bid=0.058, ask=0.0581)
        ticker_eth = _make_ticker(exchange, "ETH/USDT", bid=3_500, ask=3_510)

        svc = _make_simulation_service(
            orderbooks={
                (exchange, "BTC/USDT"): ob_btc,
                (exchange, "ETH/BTC"): ob_ethbtc,
                (exchange, "ETH/USDT"): ob_eth,
            },
            tickers={
                (exchange, "BTC/USDT"): ticker_btc,
                (exchange, "ETH/BTC"): ticker_ethbtc,
                (exchange, "ETH/USDT"): ticker_eth,
            },
        )

        opp = OpportunityCandidate(
            strategy_type="TRIANGULAR",
            symbol="BTC/USDT>ETH/BTC>ETH/USDT",
            symbols=["BTC/USDT", "ETH/BTC", "ETH/USDT"],
            exchanges=[exchange],
            buy_exchange=exchange,
            sell_exchange=exchange,
            executable_value_usdt=1000.0,
        )

        result = await svc.simulate_triangular(opp)

        assert result.strategy_type == "TRIANGULAR"
        assert len(result.legs) == 3
        assert result.entry_value_usdt == pytest.approx(1000.0)
        assert result.exit_value_usdt > 0
        assert result.total_fees_usdt > 0
        # Whether profitable depends on the cross rate -- just verify the path completes
        assert result.reason != ""

    @pytest.mark.asyncio
    async def test_simulate_triangular_missing_symbol(self):
        """Triangular with fewer than 3 symbols -> infeasible."""
        svc = _make_simulation_service()

        opp = OpportunityCandidate(
            strategy_type="TRIANGULAR",
            symbol="BTC/USDT>ETH/BTC",
            symbols=["BTC/USDT", "ETH/BTC"],  # only 2
            exchanges=["test_ex"],
        )

        result = await svc.simulate_triangular(opp)
        assert result.feasible is False
        assert "3 symbols" in result.reason
