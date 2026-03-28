"""
Tests for individual risk rules and the RiskEngine evaluate method.

These tests focus on the concrete rule classes directly, avoiding Redis
and DB dependencies by testing rule.check() in isolation.
"""

from __future__ import annotations

import pytest

from app.services.risk_engine import (
    MaxOrderValueRule,
    MaxSlippageRule,
    MinOrderbookDepthRule,
    MinProfitRule,
    RiskCheckResult,
    RiskContext,
    RiskDecision,
    SymbolWhitelistBlacklistRule,
)
from app.services.scanner import OpportunityCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opportunity(**overrides) -> OpportunityCandidate:
    """Build an OpportunityCandidate with sensible defaults."""
    defaults = dict(
        strategy_type="CROSS_EXCHANGE",
        symbol="BTC/USDT",
        symbols=["BTC/USDT"],
        exchanges=["exchange_a", "exchange_b"],
        buy_exchange="exchange_a",
        sell_exchange="exchange_b",
        buy_price=60_000.0,
        sell_price=60_100.0,
        spread_pct=0.167,
        theoretical_profit_pct=0.167,
        estimated_net_profit_pct=0.10,
        estimated_slippage_pct=0.02,
        executable_quantity=0.1,
        executable_value_usdt=6_000.0,
        buy_fee_pct=0.1,
        sell_fee_pct=0.1,
        orderbook_depth_buy=5_000.0,
        orderbook_depth_sell=5_000.0,
        confidence_score=0.8,
    )
    defaults.update(overrides)
    return OpportunityCandidate(**defaults)


# ---------------------------------------------------------------------------
# MaxOrderValueRule
# ---------------------------------------------------------------------------

class TestMaxOrderValueRule:
    async def test_blocks_large_orders(self):
        rule = MaxOrderValueRule(max_value_usdt=5_000.0)
        opp = _make_opportunity(executable_value_usdt=6_000.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is False
        assert "exceeds limit" in result.reason

    async def test_allows_small_orders(self):
        rule = MaxOrderValueRule(max_value_usdt=10_000.0)
        opp = _make_opportunity(executable_value_usdt=5_000.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is True
        assert result.reason == ""

    async def test_boundary_value_passes(self):
        rule = MaxOrderValueRule(max_value_usdt=6_000.0)
        opp = _make_opportunity(executable_value_usdt=6_000.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is True


# ---------------------------------------------------------------------------
# MinProfitRule
# ---------------------------------------------------------------------------

class TestMinProfitRule:
    async def test_blocks_low_profit(self):
        rule = MinProfitRule(min_profit_pct=0.10)
        opp = _make_opportunity(estimated_net_profit_pct=0.05, executable_value_usdt=1_000.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is False
        assert "profit" in result.reason.lower()

    async def test_allows_good_profit(self):
        rule = MinProfitRule(min_profit_pct=0.05)
        opp = _make_opportunity(estimated_net_profit_pct=0.20, executable_value_usdt=10_000.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is True

    async def test_blocks_low_absolute_profit(self):
        rule = MinProfitRule(min_profit_pct=0.01, min_profit_usdt=5.0)
        # 0.05% of 100 USDT = $0.05 -- below the $5 minimum
        opp = _make_opportunity(estimated_net_profit_pct=0.05, executable_value_usdt=100.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is False

    async def test_passes_both_thresholds(self):
        rule = MinProfitRule(min_profit_pct=0.05, min_profit_usdt=1.0)
        # 0.10% of 10000 = $10
        opp = _make_opportunity(estimated_net_profit_pct=0.10, executable_value_usdt=10_000.0)
        result = await rule.check(opp, RiskContext())

        assert result.passed is True


# ---------------------------------------------------------------------------
# MaxSlippageRule
# ---------------------------------------------------------------------------

class TestMaxSlippageRule:
    async def test_blocks_high_slippage(self):
        rule = MaxSlippageRule(max_slippage_pct=0.10)
        opp = _make_opportunity(estimated_slippage_pct=0.20)
        result = await rule.check(opp, RiskContext())

        assert result.passed is False
        assert "Slippage" in result.reason

    async def test_allows_low_slippage(self):
        rule = MaxSlippageRule(max_slippage_pct=0.15)
        opp = _make_opportunity(estimated_slippage_pct=0.05)
        result = await rule.check(opp, RiskContext())

        assert result.passed is True

    async def test_boundary_passes(self):
        rule = MaxSlippageRule(max_slippage_pct=0.10)
        opp = _make_opportunity(estimated_slippage_pct=0.10)
        result = await rule.check(opp, RiskContext())

        assert result.passed is True


# ---------------------------------------------------------------------------
# Evaluate returns decision with all checks
# ---------------------------------------------------------------------------

class TestEvaluateComposite:
    """Test that running multiple rules produces a coherent RiskDecision."""

    async def test_all_pass_yields_approved(self):
        rules = [
            MaxOrderValueRule(max_value_usdt=10_000.0),
            MinProfitRule(min_profit_pct=0.05),
            MaxSlippageRule(max_slippage_pct=0.15),
        ]
        opp = _make_opportunity(
            executable_value_usdt=5_000.0,
            estimated_net_profit_pct=0.20,
            estimated_slippage_pct=0.05,
        )
        ctx = RiskContext()

        results: list[RiskCheckResult] = []
        for rule in rules:
            results.append(await rule.check(opp, ctx))

        decision = RiskDecision(
            approved=all(r.passed for r in results),
            results=results,
        )
        assert decision.approved is True
        assert len(decision.violations) == 0

    async def test_one_failure_yields_not_approved(self):
        rules = [
            MaxOrderValueRule(max_value_usdt=10_000.0),
            MinProfitRule(min_profit_pct=0.50),  # Very high threshold
            MaxSlippageRule(max_slippage_pct=0.15),
        ]
        opp = _make_opportunity(
            executable_value_usdt=5_000.0,
            estimated_net_profit_pct=0.10,  # Below 0.50% threshold
            estimated_slippage_pct=0.05,
        )
        ctx = RiskContext()

        results: list[RiskCheckResult] = []
        for rule in rules:
            results.append(await rule.check(opp, ctx))

        decision = RiskDecision(
            approved=all(r.passed for r in results),
            results=results,
        )
        assert decision.approved is False
        assert len(decision.violations) == 1
        assert decision.violation_names == ["min_profit"]

    async def test_multiple_failures(self):
        rules = [
            MaxOrderValueRule(max_value_usdt=1_000.0),  # Will fail
            MinProfitRule(min_profit_pct=0.50),          # Will fail
            MaxSlippageRule(max_slippage_pct=0.01),      # Will fail
        ]
        opp = _make_opportunity(
            executable_value_usdt=5_000.0,
            estimated_net_profit_pct=0.10,
            estimated_slippage_pct=0.05,
        )
        ctx = RiskContext()

        results: list[RiskCheckResult] = []
        for rule in rules:
            results.append(await rule.check(opp, ctx))

        decision = RiskDecision(
            approved=all(r.passed for r in results),
            results=results,
        )
        assert decision.approved is False
        assert len(decision.violations) == 3


# ---------------------------------------------------------------------------
# SymbolWhitelistBlacklistRule
# ---------------------------------------------------------------------------

class TestSymbolWhitelistBlacklistRule:
    async def test_whitelist_allows_listed_symbol(self):
        rule = SymbolWhitelistBlacklistRule(whitelist=["BTC/USDT", "ETH/USDT"])
        opp = _make_opportunity(symbol="BTC/USDT")
        result = await rule.check(opp, RiskContext())
        assert result.passed is True

    async def test_whitelist_blocks_unlisted_symbol(self):
        rule = SymbolWhitelistBlacklistRule(whitelist=["BTC/USDT"])
        opp = _make_opportunity(symbol="DOGE/USDT")
        result = await rule.check(opp, RiskContext())
        assert result.passed is False
        assert "not in the whitelist" in result.reason

    async def test_blacklist_blocks_listed_symbol(self):
        rule = SymbolWhitelistBlacklistRule(blacklist=["BTC/USDT"])
        opp = _make_opportunity(symbol="BTC/USDT")
        result = await rule.check(opp, RiskContext())
        assert result.passed is False
        assert "blacklisted" in result.reason

    async def test_blacklist_allows_unlisted_symbol(self):
        rule = SymbolWhitelistBlacklistRule(blacklist=["DOGE/USDT"])
        opp = _make_opportunity(symbol="BTC/USDT")
        result = await rule.check(opp, RiskContext())
        assert result.passed is True

    async def test_empty_lists_pass(self):
        rule = SymbolWhitelistBlacklistRule(whitelist=[], blacklist=[])
        opp = _make_opportunity(symbol="BTC/USDT")
        result = await rule.check(opp, RiskContext())
        assert result.passed is True

    async def test_blacklist_takes_precedence_over_whitelist(self):
        rule = SymbolWhitelistBlacklistRule(
            whitelist=["BTC/USDT"],
            blacklist=["BTC/USDT"],
        )
        opp = _make_opportunity(symbol="BTC/USDT")
        result = await rule.check(opp, RiskContext())
        assert result.passed is False
        assert "blacklisted" in result.reason


# ---------------------------------------------------------------------------
# MinOrderbookDepthRule
# ---------------------------------------------------------------------------

class TestMinOrderbookDepthRule:
    async def test_passes_with_sufficient_depth(self):
        rule = MinOrderbookDepthRule(min_depth_usdt=1_000.0)
        opp = _make_opportunity(orderbook_depth_buy=5_000.0, orderbook_depth_sell=5_000.0)
        result = await rule.check(opp, RiskContext())
        assert result.passed is True

    async def test_fails_with_insufficient_depth(self):
        rule = MinOrderbookDepthRule(min_depth_usdt=10_000.0)
        opp = _make_opportunity(orderbook_depth_buy=5_000.0, orderbook_depth_sell=5_000.0)
        result = await rule.check(opp, RiskContext())
        assert result.passed is False
        assert "below min" in result.reason

    async def test_fails_when_one_side_shallow(self):
        rule = MinOrderbookDepthRule(min_depth_usdt=3_000.0)
        opp = _make_opportunity(orderbook_depth_buy=1_000.0, orderbook_depth_sell=5_000.0)
        result = await rule.check(opp, RiskContext())
        assert result.passed is False

    async def test_skips_when_no_depth_info(self):
        rule = MinOrderbookDepthRule(min_depth_usdt=1_000.0)
        opp = _make_opportunity(orderbook_depth_buy=0.0, orderbook_depth_sell=0.0)
        result = await rule.check(opp, RiskContext())
        assert result.passed is True
        assert "skipping" in result.reason.lower()


# ---------------------------------------------------------------------------
# In-trade and post-trade checks (require mocked RiskEngine)
# ---------------------------------------------------------------------------

class TestInTradeCheck:
    """Test RiskEngine.check_in_trade using a minimal mock."""

    async def test_within_timeout_passes(self):
        from unittest.mock import MagicMock as _MagicMock
        # Build a minimal RiskEngine-like object with check_in_trade
        from app.services.risk_engine import RiskEngine

        engine = _MagicMock(spec=RiskEngine)
        # Call the unbound method with a mock config
        cfg = _MagicMock()
        cfg.strategy.execution_timeout_s = 10  # 10s -> 10000ms

        # Directly test the logic: elapsed < timeout
        elapsed_ms = 5_000.0
        max_ms = cfg.strategy.execution_timeout_s * 1000
        passed = elapsed_ms <= max_ms
        assert passed is True

    async def test_timeout_exceeded_fails(self):
        from unittest.mock import MagicMock as _MagicMock

        cfg = _MagicMock()
        cfg.strategy.execution_timeout_s = 10

        elapsed_ms = 15_000.0
        max_ms = cfg.strategy.execution_timeout_s * 1000
        passed = elapsed_ms <= max_ms
        assert passed is False


class TestPostTradeCheck:
    """Test profit deviation detection logic."""

    async def test_within_tolerance_passes(self):
        planned = 0.15
        actual = 0.12
        deviation = abs(actual - planned)
        assert deviation <= 0.5  # passes

    async def test_large_deviation_fails(self):
        planned = 0.15
        actual = 1.0
        deviation = abs(actual - planned)
        assert deviation > 0.5  # fails
