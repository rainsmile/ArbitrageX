"""Tests for the ExecutionPlanner."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.execution_planner import ExecutionLegPlan, ExecutionPlanData, ExecutionPlanner
from app.services.inventory import BalanceSnapshot, ExchangeAllocation
from app.services.risk_engine import RiskCheckResult, RiskContext, RiskDecision
from app.services.scanner import OpportunityCandidate
from app.services.simulation import SimulationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opportunity(**overrides) -> OpportunityCandidate:
    defaults = dict(
        strategy_type="CROSS_EXCHANGE",
        symbol="BTC/USDT",
        symbols=["BTC/USDT"],
        exchanges=["binance", "okx"],
        buy_exchange="binance",
        sell_exchange="okx",
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
        detected_at=time.time(),
    )
    defaults.update(overrides)
    return OpportunityCandidate(**defaults)


def _approved_decision() -> RiskDecision:
    return RiskDecision(
        approved=True,
        results=[RiskCheckResult(rule_name="test", passed=True)],
    )


def _rejected_decision() -> RiskDecision:
    return RiskDecision(
        approved=False,
        results=[RiskCheckResult(rule_name="test_rule", passed=False, reason="blocked")],
    )


def _mock_simulation_result() -> SimulationResult:
    return SimulationResult(
        strategy_type="CROSS_EXCHANGE",
        entry_value_usdt=6_000.0,
        gross_profit_usdt=10.0,
        net_profit_usdt=8.0,
        total_fees_usdt=2.0,
        total_slippage_usdt=0.5,
        feasible=True,
    )


def _build_planner(
    risk_decision: RiskDecision | None = None,
    buy_balance: BalanceSnapshot | None = None,
    sell_balance: BalanceSnapshot | None = None,
) -> ExecutionPlanner:
    """Build an ExecutionPlanner with mocked dependencies."""
    risk_engine = AsyncMock()
    risk_engine.evaluate = AsyncMock(return_value=risk_decision or _approved_decision())

    inventory = MagicMock()
    inventory.get_balance = MagicMock(side_effect=lambda exch, asset: {
        ("binance", "USDT"): buy_balance or BalanceSnapshot(
            exchange="binance", asset="USDT", free=100_000.0, locked=0.0, total=100_000.0,
        ),
        ("okx", "BTC"): sell_balance or BalanceSnapshot(
            exchange="okx", asset="BTC", free=1.0, locked=0.0, total=1.0,
        ),
    }.get((exch, asset)))
    inventory.get_exchange_allocation = MagicMock(return_value=[
        ExchangeAllocation(exchange="binance", total_value_usdt=50_000.0),
        ExchangeAllocation(exchange="okx", total_value_usdt=50_000.0),
    ])

    market_data = MagicMock()
    market_data.get_ticker = MagicMock(return_value=None)
    market_data.get_data_age = MagicMock(return_value=1.0)

    simulation = AsyncMock()
    simulation.simulate_cross_exchange = AsyncMock(return_value=_mock_simulation_result())
    simulation.simulate_triangular = AsyncMock(return_value=_mock_simulation_result())

    return ExecutionPlanner(
        risk_engine=risk_engine,
        inventory_manager=inventory,
        market_data=market_data,
        simulation_service=simulation,
    )


# ---------------------------------------------------------------------------
# Cross-exchange plan
# ---------------------------------------------------------------------------

class TestBuildCrossExchangePlan:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        planner = _build_planner()
        opp = _make_opportunity()
        plan = await planner.build_cross_exchange_plan(opp)

        assert isinstance(plan, ExecutionPlanData)
        assert plan.strategy_type == "CROSS_EXCHANGE"
        assert plan.mode == "PAPER"
        assert len(plan.legs) == 2
        assert plan.legs[0].side == "BUY"
        assert plan.legs[1].side == "SELL"
        assert plan.risk_check.approved is True
        assert plan.plan_id  # non-empty
        assert plan.opportunity_id == opp.id

    @pytest.mark.asyncio
    async def test_plan_has_required_fields(self):
        planner = _build_planner()
        opp = _make_opportunity()
        plan = await planner.build_cross_exchange_plan(opp)

        d = plan.to_dict()
        assert "plan_id" in d
        assert "legs" in d
        assert d["leg_count"] == 2
        assert "risk_approved" in d
        assert "planned_net_profit" in d

    @pytest.mark.asyncio
    async def test_risk_rejected_still_returns_plan(self):
        planner = _build_planner(risk_decision=_rejected_decision())
        opp = _make_opportunity()
        plan = await planner.build_cross_exchange_plan(opp)

        assert plan.risk_check.approved is False
        assert len(plan.risk_check.violations) == 1

    @pytest.mark.asyncio
    async def test_stale_opportunity_still_builds(self):
        planner = _build_planner()
        opp = _make_opportunity(detected_at=time.time() - 30.0)  # 30s old
        plan = await planner.build_cross_exchange_plan(opp)
        assert plan.plan_id  # plan still created despite staleness

    @pytest.mark.asyncio
    async def test_quantity_constrained_by_balance(self):
        # Small USDT balance limits buy quantity
        small_balance = BalanceSnapshot(
            exchange="binance", asset="USDT", free=600.0, locked=0.0, total=600.0,
        )
        planner = _build_planner(buy_balance=small_balance)
        opp = _make_opportunity(executable_quantity=0.1, buy_price=60_000.0)
        plan = await planner.build_cross_exchange_plan(opp)

        # 600 USDT / 60000 = 0.01 BTC max, constrained from 0.1
        assert plan.target_quantity <= 0.01 + 1e-9

    @pytest.mark.asyncio
    async def test_leg_exchange_assignment(self):
        planner = _build_planner()
        opp = _make_opportunity()
        plan = await planner.build_cross_exchange_plan(opp)

        assert plan.legs[0].exchange == "binance"
        assert plan.legs[1].exchange == "okx"

    @pytest.mark.asyncio
    async def test_simulation_failure_does_not_crash(self):
        planner = _build_planner()
        planner._simulation.simulate_cross_exchange = AsyncMock(side_effect=RuntimeError("sim failed"))
        opp = _make_opportunity()
        plan = await planner.build_cross_exchange_plan(opp)
        assert plan.simulation_result is None


# ---------------------------------------------------------------------------
# Triangular plan
# ---------------------------------------------------------------------------

class TestBuildTriangularPlan:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        planner = _build_planner()
        opp = _make_opportunity(
            strategy_type="TRIANGULAR",
            symbol="BTC/USDT>ETH/BTC>ETH/USDT",
            symbols=["BTC/USDT", "ETH/BTC", "ETH/USDT"],
            exchanges=["binance"],
            buy_exchange="binance",
            sell_exchange="binance",
        )
        plan = await planner.build_triangular_plan(opp)

        assert plan.strategy_type == "TRIANGULAR"
        assert len(plan.legs) == 3

    @pytest.mark.asyncio
    async def test_requires_three_symbols(self):
        planner = _build_planner()
        opp = _make_opportunity(
            strategy_type="TRIANGULAR",
            symbols=["BTC/USDT", "ETH/BTC"],  # only 2
        )
        with pytest.raises(ValueError, match="3 symbols"):
            await planner.build_triangular_plan(opp)

    @pytest.mark.asyncio
    async def test_triangular_plan_to_dict(self):
        planner = _build_planner()
        opp = _make_opportunity(
            strategy_type="TRIANGULAR",
            symbol="BTC/USDT>ETH/BTC>ETH/USDT",
            symbols=["BTC/USDT", "ETH/BTC", "ETH/USDT"],
            exchanges=["binance"],
        )
        plan = await planner.build_triangular_plan(opp)
        d = plan.to_dict()
        assert d["strategy_type"] == "TRIANGULAR"
        assert d["leg_count"] == 3
