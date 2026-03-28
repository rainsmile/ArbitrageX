"""Tests for core calculation functions -- the math engine of the arbitrage system.

Every test uses concrete, hand-verifiable numbers.
"""

from __future__ import annotations

import math

import pytest

from app.core.calculations import (
    DepthWalkResult,
    compute_executable_quantity,
    compute_net_profit,
    compute_spread,
    compute_triangular_profit,
    estimate_fee,
    estimate_slippage,
    score_opportunity_confidence,
    truncate_to_step_size,
    walk_orderbook_depth,
)


# =====================================================================
# walk_orderbook_depth
# =====================================================================

class TestWalkOrderbookDepth:
    """Tests for walk_orderbook_depth."""

    def test_walk_single_level(self):
        """Fill completely from one ask level."""
        asks = [(100.0, 5.0)]
        r = walk_orderbook_depth(asks, 3.0, "buy")

        assert r.filled_quantity == 3.0
        assert r.average_price == 100.0
        assert r.total_cost == 300.0  # 3 * 100
        assert r.levels_consumed == 1
        assert r.is_fully_filled is True
        assert r.shortfall_quantity == 0.0
        assert r.worst_price == 100.0
        assert r.price_impact_pct == 0.0  # single level, no impact

    def test_walk_multiple_levels(self):
        """Fill across multiple levels: 1@100 + 2@101 + 2.5@102 = 5.5 units."""
        asks = [(100.0, 1.0), (101.0, 2.0), (102.0, 3.0), (103.0, 2.0), (104.0, 1.0)]
        r = walk_orderbook_depth(asks, 5.5, "buy")

        # 1*100 + 2*101 + 2.5*102 = 100 + 202 + 255 = 557
        assert r.filled_quantity == 5.5
        assert r.total_cost == pytest.approx(557.0)
        assert r.average_price == pytest.approx(557.0 / 5.5)  # ~101.2727
        assert r.levels_consumed == 3
        assert r.is_fully_filled is True
        assert r.worst_price == 102.0

    def test_walk_exact_quantity_from_docstring(self):
        """Reproduce the docstring example: 2.5 units from 3-level book."""
        asks = [(100.0, 1.0), (101.0, 2.0), (102.0, 3.0)]
        r = walk_orderbook_depth(asks, 2.5, "buy")

        # 1@100 + 1.5@101 = 100 + 151.5 = 251.5
        assert r.filled_quantity == 2.5
        assert r.total_cost == pytest.approx(251.5)
        assert round(r.average_price, 4) == 100.6  # 251.5 / 2.5
        assert r.levels_consumed == 2
        assert r.is_fully_filled is True

    def test_walk_partial_fill(self):
        """Target exceeds total depth -- only partial fill."""
        asks = [(100.0, 1.0), (101.0, 1.0)]  # total depth = 2.0
        r = walk_orderbook_depth(asks, 5.0, "buy")

        assert r.filled_quantity == 2.0
        assert r.total_cost == pytest.approx(201.0)  # 1*100 + 1*101
        assert r.is_fully_filled is False
        assert r.shortfall_quantity == pytest.approx(3.0)
        assert r.levels_consumed == 2

    def test_walk_empty_book(self):
        """Empty levels list returns zero fill."""
        r = walk_orderbook_depth([], 1.0, "buy")

        assert r.filled_quantity == 0.0
        assert r.average_price == 0.0
        assert r.total_cost == 0.0
        assert r.levels_consumed == 0
        assert r.is_fully_filled is False
        assert r.shortfall_quantity == 1.0

    def test_walk_exact_fill(self):
        """Target exactly matches the first level's quantity."""
        asks = [(50.0, 2.0), (51.0, 3.0)]
        r = walk_orderbook_depth(asks, 2.0, "buy")

        assert r.filled_quantity == 2.0
        assert r.total_cost == 100.0
        assert r.average_price == 50.0
        assert r.levels_consumed == 1
        assert r.is_fully_filled is True
        assert r.price_impact_pct == 0.0

    def test_walk_price_impact(self):
        """Verify price impact = |avg - best| / best * 100."""
        asks = [(100.0, 1.0), (110.0, 1.0)]
        r = walk_orderbook_depth(asks, 2.0, "buy")

        # avg = (100 + 110) / 2 = 105, best = 100
        # impact = |105 - 100| / 100 * 100 = 5%
        assert r.average_price == pytest.approx(105.0)
        assert r.price_impact_pct == pytest.approx(5.0)

    def test_walk_buy_vs_sell(self):
        """Buy walks asks ascending, sell walks bids descending.

        The function doesn't sort -- it trusts the caller to provide
        correct ordering. We verify the same function works for both sides
        with appropriately ordered data.
        """
        # Buy side: asks ascending
        asks = [(100.0, 1.0), (101.0, 1.0)]
        r_buy = walk_orderbook_depth(asks, 2.0, "buy")
        assert r_buy.average_price == pytest.approx(100.5)

        # Sell side: bids descending (highest first)
        bids = [(101.0, 1.0), (100.0, 1.0)]
        r_sell = walk_orderbook_depth(bids, 2.0, "sell")
        assert r_sell.average_price == pytest.approx(100.5)

    def test_walk_zero_target(self):
        """Zero target quantity returns immediately with is_fully_filled=True."""
        asks = [(100.0, 1.0)]
        r = walk_orderbook_depth(asks, 0.0, "buy")
        assert r.filled_quantity == 0.0
        assert r.is_fully_filled is True

    def test_walk_negative_target(self):
        """Negative target returns zero fill with is_fully_filled=True."""
        asks = [(100.0, 1.0)]
        r = walk_orderbook_depth(asks, -1.0, "buy")
        assert r.filled_quantity == 0.0
        assert r.is_fully_filled is True


# =====================================================================
# estimate_fee
# =====================================================================

class TestEstimateFee:
    """Tests for estimate_fee."""

    def test_fee_basic(self):
        """0.1% on $10,000 notional = $10."""
        f = estimate_fee(quantity=1.0, price=10_000.0, fee_rate=0.001)
        assert f.fee_amount == pytest.approx(10.0)
        assert f.fee_rate == 0.001
        assert f.fee_asset == "USDT"

    def test_fee_zero_rate(self):
        """Zero fee rate produces zero fee."""
        f = estimate_fee(quantity=5.0, price=200.0, fee_rate=0.0)
        assert f.fee_amount == 0.0

    def test_fee_high_rate(self):
        """0.5% on $60,000 = $300."""
        f = estimate_fee(quantity=1.0, price=60_000.0, fee_rate=0.005)
        assert f.fee_amount == pytest.approx(300.0)

    def test_fee_custom_quote_asset(self):
        """Quote asset propagates to the result."""
        f = estimate_fee(quantity=1.0, price=100.0, fee_rate=0.001, quote_asset="BTC")
        assert f.fee_asset == "BTC"


# =====================================================================
# estimate_slippage
# =====================================================================

class TestEstimateSlippage:
    """Tests for estimate_slippage."""

    def test_slippage_no_impact(self):
        """avg_price equals best_price: natural slippage = 0."""
        s = estimate_slippage(best_price=100.0, avg_fill_price=100.0, side="buy", buffer_bps=0.0)
        assert s.natural_slippage_pct == 0.0
        assert s.buffer_slippage_pct == 0.0
        assert s.total_slippage_pct == 0.0
        assert s.slippage_cost == 0.0

    def test_slippage_with_impact(self):
        """avg_price 100.5 vs best 100.0: 0.5% natural slippage."""
        s = estimate_slippage(best_price=100.0, avg_fill_price=100.5, side="buy", buffer_bps=0.0)
        assert s.natural_slippage_pct == pytest.approx(0.5)
        assert s.total_slippage_pct == pytest.approx(0.5)
        # cost = 0.5% / 100 * 100 = 0.5 per unit
        assert s.slippage_cost == pytest.approx(0.5)

    def test_slippage_with_buffer(self):
        """Reproduce the docstring example: 0.5% natural + 5bps buffer = 0.55%."""
        s = estimate_slippage(best_price=100.0, avg_fill_price=100.5, side="buy", buffer_bps=5.0)
        assert round(s.natural_slippage_pct, 2) == 0.5
        assert round(s.buffer_slippage_pct, 2) == 0.05
        assert round(s.total_slippage_pct, 2) == 0.55
        # cost = 0.55% / 100 * 100 = 0.55
        assert s.slippage_cost == pytest.approx(0.55)

    def test_slippage_sell_side(self):
        """Sell side: avg_price < best_price still gives positive slippage."""
        s = estimate_slippage(best_price=100.0, avg_fill_price=99.5, side="sell", buffer_bps=0.0)
        assert s.natural_slippage_pct == pytest.approx(0.5)

    def test_slippage_zero_best_price(self):
        """Zero best price returns zero slippage (edge case)."""
        s = estimate_slippage(best_price=0.0, avg_fill_price=100.0, side="buy")
        assert s.total_slippage_pct == 0.0
        assert s.slippage_cost == 0.0


# =====================================================================
# truncate_to_step_size
# =====================================================================

class TestTruncateToStepSize:
    """Tests for truncate_to_step_size helper."""

    def test_truncate_basic(self):
        assert truncate_to_step_size(1.23456, 0.001) == 1.234

    def test_truncate_round_down(self):
        assert truncate_to_step_size(0.999, 0.01) == 0.99

    def test_truncate_exact(self):
        assert truncate_to_step_size(5.0, 0.1) == 5.0

    def test_truncate_zero_step(self):
        """Zero step returns quantity unchanged."""
        assert truncate_to_step_size(5.123, 0.0) == 5.123


# =====================================================================
# compute_executable_quantity
# =====================================================================

class TestComputeExecutableQuantity:
    """Tests for compute_executable_quantity."""

    def test_executable_basic(self):
        """Both sides have depth, balance sufficient."""
        asks = [(100.0, 5.0), (101.0, 5.0)]
        bids = [(102.0, 5.0), (101.5, 5.0)]
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=10_000.0,
            sell_balance_base=10.0,
            max_notional_usdt=100_000.0,
        )
        # Buy side: total depth = 10, balance can buy 10000/100 = up to 100 units
        # But asks only have 10 units. Sell side: 10 units depth, 10 base.
        # qty = min(10, 10) = 10
        assert r.quantity == pytest.approx(10.0)
        assert r.buy_depth_sufficient is True
        assert r.sell_depth_sufficient is True

    def test_executable_limited_by_buy_depth(self):
        """Buy side has less depth than sell side."""
        asks = [(100.0, 2.0)]  # only 2 units available
        bids = [(102.0, 10.0)]
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=100_000.0,
            sell_balance_base=10.0,
        )
        assert r.quantity == pytest.approx(2.0)
        assert r.limited_by == "buy_depth"

    def test_executable_limited_by_sell_depth(self):
        """Sell side has less depth than buy side."""
        asks = [(100.0, 10.0)]
        bids = [(102.0, 3.0)]  # only 3 units
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=100_000.0,
            sell_balance_base=10.0,
        )
        assert r.quantity == pytest.approx(3.0)
        assert r.limited_by == "sell_depth"

    def test_executable_limited_by_balance(self):
        """Buy balance constrains quantity."""
        asks = [(100.0, 5.0), (101.0, 5.0)]
        bids = [(102.0, 5.0), (101.5, 5.0)]
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=500.0,  # can afford ~5 units at 100
            sell_balance_base=10.0,
        )
        assert r.quantity == pytest.approx(5.0)
        assert r.limited_by == "balance"

    def test_executable_limited_by_max_notional(self):
        """Max notional cap limits quantity."""
        asks = [(100.0, 100.0)]
        bids = [(102.0, 100.0)]
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=1_000_000.0,
            sell_balance_base=100.0,
            max_notional_usdt=500.0,  # 500 / 100 = max 5 units
        )
        assert r.quantity == pytest.approx(5.0)
        assert r.limited_by == "max_notional"

    def test_executable_below_min_quantity(self):
        """Result below min_quantity returns 0."""
        asks = [(100.0, 0.5)]
        bids = [(102.0, 10.0)]
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=100_000.0,
            sell_balance_base=10.0,
            min_quantity=1.0,  # 0.5 < 1.0
        )
        assert r.quantity == 0.0
        assert r.limited_by == "min_quantity"

    def test_executable_step_size_truncation(self):
        """Quantity is truncated to step size."""
        asks = [(100.0, 10.0)]
        bids = [(102.0, 10.0)]
        r = compute_executable_quantity(
            buy_asks=asks,
            sell_bids=bids,
            buy_balance_quote=355.0,  # 355/100 = 3.55 units
            sell_balance_base=10.0,
            step_size=0.1,
        )
        assert r.quantity == pytest.approx(3.5)  # truncated from 3.55


# =====================================================================
# compute_net_profit
# =====================================================================

class TestComputeNetProfit:
    """Tests for compute_net_profit."""

    def test_profit_basic(self):
        """Simple case: buy@100, sell@102, no fees, no slippage buffer."""
        r = compute_net_profit(
            buy_quantity=1.0, buy_avg_price=100.0,
            sell_quantity=1.0, sell_avg_price=102.0,
            buy_fee_rate=0.0, sell_fee_rate=0.0,
            slippage_buffer_bps=0.0,
            buy_best_price=100.0, sell_best_price=102.0,
        )
        assert r.gross_profit == pytest.approx(2.0)
        assert r.gross_profit_pct == pytest.approx(2.0)
        assert r.net_profit == pytest.approx(2.0)
        assert r.is_profitable is True

    def test_profit_with_fees(self):
        """Fees deducted: buy@100, sell@102, 0.1% each side."""
        r = compute_net_profit(
            buy_quantity=1.0, buy_avg_price=100.0,
            sell_quantity=1.0, sell_avg_price=102.0,
            buy_fee_rate=0.001, sell_fee_rate=0.001,
            slippage_buffer_bps=0.0,
            buy_best_price=100.0, sell_best_price=102.0,
        )
        # buy_fee = 100 * 0.001 = 0.1
        # sell_fee = 102 * 0.001 = 0.102
        # net = 2.0 - 0.1 - 0.102 = 1.798
        assert r.buy_fee == pytest.approx(0.1)
        assert r.sell_fee == pytest.approx(0.102)
        assert r.total_fees == pytest.approx(0.202)
        assert r.net_profit == pytest.approx(1.798)
        assert r.is_profitable is True

    def test_profit_negative(self):
        """Spread too small after fees -> not profitable."""
        r = compute_net_profit(
            buy_quantity=1.0, buy_avg_price=100.0,
            sell_quantity=1.0, sell_avg_price=100.1,
            buy_fee_rate=0.001, sell_fee_rate=0.001,
            slippage_buffer_bps=5.0,
            buy_best_price=100.0, sell_best_price=100.1,
        )
        # gross = 0.1
        # fees = 100*0.001 + 100.1*0.001 = 0.1 + 0.1001 = 0.2001
        # slippage buffer: both best==avg so natural=0, buffer only
        # buffer = 5bps = 0.05%, cost_buy = 0.05/100*100 = 0.05 per unit * 1 = 0.05
        # cost_sell = 0.05/100*100.1 = 0.05005 per unit * 1 = 0.05005
        # total_slippage = 0.05 + 0.05005 = 0.10005
        # net = 0.1 - 0.2001 - 0.10005 = -0.20015
        assert r.is_profitable is False
        assert r.net_profit < 0

    def test_profit_breakeven_spread(self):
        """Breakeven spread = (buy_fee_rate + sell_fee_rate)*100 + 2*buffer_bps/100."""
        r = compute_net_profit(
            buy_quantity=1.0, buy_avg_price=100.0,
            sell_quantity=1.0, sell_avg_price=100.0,
            buy_fee_rate=0.001, sell_fee_rate=0.001,
            slippage_buffer_bps=5.0,
        )
        # breakeven = (0.001+0.001)*100 + 5/100*2 = 0.2 + 0.1 = 0.3%
        assert r.breakeven_spread_pct == pytest.approx(0.3)

    def test_profit_defaults_best_to_avg(self):
        """When best_price is 0, it defaults to avg_price -> zero natural slippage."""
        r = compute_net_profit(
            buy_quantity=1.0, buy_avg_price=100.0,
            sell_quantity=1.0, sell_avg_price=102.0,
            buy_fee_rate=0.0, sell_fee_rate=0.0,
            slippage_buffer_bps=0.0,
            buy_best_price=0.0,  # should default to 100
            sell_best_price=0.0,  # should default to 102
        )
        assert r.total_slippage_cost == 0.0
        assert r.net_profit == pytest.approx(2.0)


# =====================================================================
# compute_triangular_profit
# =====================================================================

class TestComputeTriangularProfit:
    """Tests for compute_triangular_profit."""

    def test_triangular_profitable(self):
        """BTC/USDT -> ETH/BTC -> ETH/USDT with an exploitable mispricing.

        Start: 10000 USDT
        Leg 1 (buy BTC): 10000 / 50000 = 0.2 BTC, after 0.1% fee = 0.1998 BTC
        Leg 2 (sell BTC for ETH): 0.1998 * 16 = 3.1968 ETH, after 0.1% fee = 3.193603 ETH
        Leg 3 (sell ETH): 3.193603 * 3200 = 10219.53 USDT, after 0.1% fee = 10209.31 USDT
        Net profit ~ 209.31 USDT (2.09%)

        The cross rate is BTC=50000, ETH/BTC=16, ETH/USDT=3200.
        Fair: 50000 / 3200 = 15.625 ETH/BTC. Getting 16 ETH/BTC is mispriced.
        """
        legs = [
            {"price": 50000.0, "side": "buy", "fee_rate": 0.001},
            {"price": 16.0, "side": "sell", "fee_rate": 0.001},
            {"price": 3200.0, "side": "sell", "fee_rate": 0.001},
        ]
        r = compute_triangular_profit(10000.0, legs)

        assert r.start_amount == 10000.0
        assert r.is_profitable is True
        assert r.net_profit > 0
        assert r.net_profit_pct > 0
        # Verify the chain: start/50000 * 16 * 3200 = start * 1.024
        # Gross should be ~240 USDT (2.4%), net less due to 3x fees
        assert r.gross_profit == pytest.approx(240.0)

    def test_triangular_unprofitable(self):
        """Fees eat the profit when cross rate is near fair value."""
        # Fair cross rate: BTC=50000, ETH/BTC = 50000/3200 = 15.625
        legs = [
            {"price": 50000.0, "side": "buy", "fee_rate": 0.001},
            {"price": 15.625, "side": "sell", "fee_rate": 0.001},
            {"price": 3200.0, "side": "sell", "fee_rate": 0.001},
        ]
        r = compute_triangular_profit(10000.0, legs)

        # Gross = 10000/50000 * 15.625 * 3200 - 10000 = 10000 - 10000 = 0
        assert r.gross_profit == pytest.approx(0.0)
        assert r.is_profitable is False
        assert r.net_profit < 0  # fees make it negative

    def test_triangular_debug_trace(self):
        """Verify debug_steps has the correct number of entries and keys."""
        legs = [
            {"price": 100.0, "side": "buy", "fee_rate": 0.001},
            {"price": 2.0, "side": "sell", "fee_rate": 0.001},
            {"price": 50.0, "side": "sell", "fee_rate": 0.001},
        ]
        r = compute_triangular_profit(1000.0, legs)

        assert len(r.debug_steps) == 3
        for i, step in enumerate(r.debug_steps):
            assert step["leg"] == i + 1
            assert "amount_in" in step
            assert "amount_out" in step
            assert "fee_deducted" in step
            assert "raw_out" in step

        # Verify first step: buy 1000/100 = 10 units, fee = 10*0.001 = 0.01
        assert r.debug_steps[0]["amount_in"] == 1000.0
        assert r.debug_steps[0]["raw_out"] == pytest.approx(10.0)
        assert r.debug_steps[0]["fee_deducted"] == pytest.approx(0.01)
        assert r.debug_steps[0]["amount_out"] == pytest.approx(9.99)

    def test_triangular_empty_legs(self):
        """No legs returns start_amount unchanged with no profit."""
        r = compute_triangular_profit(1000.0, [])
        assert r.end_amount == 1000.0
        assert r.net_profit == 0.0
        assert r.is_profitable is False


# =====================================================================
# compute_spread
# =====================================================================

class TestComputeSpread:
    """Tests for compute_spread."""

    def test_spread_positive(self):
        """Bid > ask: arbitrage exists."""
        spread_abs, spread_pct = compute_spread(102.0, 100.0)
        assert spread_abs == pytest.approx(2.0)
        assert spread_pct == pytest.approx(2.0)  # 2/100 * 100

    def test_spread_negative(self):
        """Bid < ask: normal market, no arb."""
        spread_abs, spread_pct = compute_spread(99.0, 100.0)
        assert spread_abs == pytest.approx(-1.0)
        assert spread_pct == pytest.approx(-1.0)

    def test_spread_zero(self):
        """Bid == ask: zero spread."""
        spread_abs, spread_pct = compute_spread(100.0, 100.0)
        assert spread_abs == 0.0
        assert spread_pct == 0.0

    def test_spread_zero_ask(self):
        """Zero ask returns 0% spread to avoid division by zero."""
        spread_abs, spread_pct = compute_spread(100.0, 0.0)
        assert spread_pct == 0.0


# =====================================================================
# score_opportunity_confidence
# =====================================================================

class TestScoreOpportunityConfidence:
    """Tests for score_opportunity_confidence."""

    def test_score_high_confidence(self):
        """High profit, full depth, fresh data, stable spread -> near 100."""
        score = score_opportunity_confidence(
            net_profit_pct=1.0,      # saturates profit at 40
            buy_depth_filled=True,   # +10
            sell_depth_filled=True,  # +10
            data_age_ms=100,         # < 500ms -> 20
            spread_stability=1.0,    # -> 20
        )
        # 40 + 10 + 10 + 20 + 20 = 100
        assert score == pytest.approx(100.0)

    def test_score_low_confidence(self):
        """Low profit, partial depth, stale data, volatile spread -> low score."""
        score = score_opportunity_confidence(
            net_profit_pct=0.05,     # sqrt(0.05) * 40 ~ 8.94
            buy_depth_filled=False,  # +0
            sell_depth_filled=True,  # +10
            data_age_ms=4000,        # 20 * (1 - 3500/4500) ~ 4.44
            spread_stability=0.2,    # 20 * 0.2 = 4
        )
        # ~8.94 + 0 + 10 + 4.44 + 4 = ~27.4
        assert 20 < score < 35

    def test_score_zero_profit(self):
        """Zero or negative profit: profit component = 0."""
        score = score_opportunity_confidence(
            net_profit_pct=0.0,
            buy_depth_filled=True,
            sell_depth_filled=True,
            data_age_ms=100,
            spread_stability=1.0,
        )
        # 0 + 10 + 10 + 20 + 20 = 60
        assert score == pytest.approx(60.0)

    def test_score_clamped_upper(self):
        """Score never exceeds 100 even with extreme inputs."""
        score = score_opportunity_confidence(
            net_profit_pct=10.0,     # clamped to 1.0 -> 40
            buy_depth_filled=True,
            sell_depth_filled=True,
            data_age_ms=0,
            spread_stability=5.0,    # clamped to 1.0 -> 20
        )
        assert score <= 100.0

    def test_score_clamped_lower(self):
        """Score never goes below 0."""
        score = score_opportunity_confidence(
            net_profit_pct=-5.0,
            buy_depth_filled=False,
            sell_depth_filled=False,
            data_age_ms=999_999,
            spread_stability=-1.0,
        )
        assert score >= 0.0

    def test_score_stale_data_penalty(self):
        """Data >= 5000ms gets 0 freshness points."""
        fresh = score_opportunity_confidence(0.5, True, True, 100, 1.0)
        stale = score_opportunity_confidence(0.5, True, True, 10_000, 1.0)
        # Stale loses 20 freshness points
        assert fresh - stale == pytest.approx(20.0)
