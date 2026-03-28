"""Tests for the ExecutionCoordinator."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.execution_coordinator import ActiveExecution, ExecutionCoordinator
from app.services.execution_engine import ExecutionResult, LegResult
from app.services.execution_planner import ExecutionLegPlan, ExecutionPlanData
from app.services.risk_engine import RiskCheckResult, RiskDecision
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


def _approved_plan_data(opp: OpportunityCandidate) -> ExecutionPlanData:
    from datetime import datetime, timezone
    return ExecutionPlanData(
        plan_id="plan-1",
        opportunity_id=opp.id,
        strategy_type="CROSS_EXCHANGE",
        mode="PAPER",
        legs=[
            ExecutionLegPlan(0, "binance", "BTC/USDT", "BUY", "MARKET", 60000.0, 0.1, 6000.0, 0.1),
            ExecutionLegPlan(1, "okx", "BTC/USDT", "SELL", "MARKET", 60100.0, 0.1, 6010.0, 0.1),
        ],
        target_quantity=0.1,
        target_notional_usdt=6000.0,
        planned_gross_profit=10.0,
        planned_net_profit=8.0,
        planned_net_profit_pct=0.133,
        risk_check=RiskDecision(approved=True, results=[
            RiskCheckResult(rule_name="test", passed=True),
        ]),
        simulation_result=None,
        pre_execution_snapshot={},
        created_at=datetime.now(timezone.utc),
    )


def _rejected_plan_data(opp: OpportunityCandidate) -> ExecutionPlanData:
    from datetime import datetime, timezone
    return ExecutionPlanData(
        plan_id="plan-1",
        opportunity_id=opp.id,
        strategy_type="CROSS_EXCHANGE",
        mode="PAPER",
        legs=[
            ExecutionLegPlan(0, "binance", "BTC/USDT", "BUY", "MARKET", 60000.0, 0.1, 6000.0, 0.1),
            ExecutionLegPlan(1, "okx", "BTC/USDT", "SELL", "MARKET", 60100.0, 0.1, 6010.0, 0.1),
        ],
        target_quantity=0.1,
        target_notional_usdt=6000.0,
        planned_gross_profit=10.0,
        planned_net_profit=8.0,
        planned_net_profit_pct=0.133,
        risk_check=RiskDecision(approved=False, results=[
            RiskCheckResult(rule_name="max_order", passed=False, reason="too large"),
        ]),
        simulation_result=None,
        pre_execution_snapshot={},
        created_at=datetime.now(timezone.utc),
    )


def _success_execution_result(opp: OpportunityCandidate) -> ExecutionResult:
    return ExecutionResult(
        opportunity_id=opp.id,
        strategy_type="CROSS_EXCHANGE",
        mode="PAPER",
        state="COMPLETED",
        legs=[
            LegResult(0, "binance", "BTC/USDT", "BUY", 60000.0, 0.1,
                      actual_price=60000.0, actual_quantity=0.1, fee=6.0, status="FILLED"),
            LegResult(1, "okx", "BTC/USDT", "SELL", 60100.0, 0.1,
                      actual_price=60100.0, actual_quantity=0.1, fee=6.01, status="FILLED"),
        ],
        actual_profit_usdt=8.0,
        gross_profit_usdt=10.0,
        total_fees_usdt=12.01,
        total_slippage_usdt=0.0,
        execution_time_ms=50.0,
        started_at=time.time(),
        completed_at=time.time(),
    )


def _build_coordinator(plan_data=None, engine_result=None) -> ExecutionCoordinator:
    opp = _make_opportunity()

    execution_engine = AsyncMock()
    execution_engine.execute = AsyncMock(
        return_value=engine_result or _success_execution_result(opp)
    )

    risk_engine = AsyncMock()
    inventory_manager = AsyncMock()
    inventory_manager.refresh_all = AsyncMock()

    alert_service = AsyncMock()
    alert_service.send_alert = AsyncMock()

    audit_service = MagicMock()
    audit_service.log = MagicMock()
    audit_service.log_execution_created = MagicMock()
    audit_service.log_risk_check = MagicMock()
    audit_service.log_state_transition = MagicMock()
    audit_service.log_leg_submitted = MagicMock()
    audit_service.log_leg_filled = MagicMock()
    audit_service.get_entries_for_execution = MagicMock(return_value=[])

    analytics_service = MagicMock()

    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()

    planner = AsyncMock()
    planner.build_cross_exchange_plan = AsyncMock(
        return_value=plan_data or _approved_plan_data(opp)
    )
    planner.build_triangular_plan = AsyncMock(
        return_value=plan_data or _approved_plan_data(opp)
    )
    # Expose _market_data for execute_cross_exchange
    planner._market_data = MagicMock()

    return ExecutionCoordinator(
        execution_engine=execution_engine,
        risk_engine=risk_engine,
        inventory_manager=inventory_manager,
        alert_service=alert_service,
        audit_service=audit_service,
        analytics_service=analytics_service,
        event_bus=event_bus,
        execution_planner=planner,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExecuteOpportunityHappyPath:
    @pytest.mark.asyncio
    async def test_returns_execution_result(self):
        coord = _build_coordinator()
        opp = _make_opportunity()
        result = await coord.execute_opportunity(opp)

        assert isinstance(result, ExecutionResult)
        assert result.state == "COMPLETED"

    @pytest.mark.asyncio
    async def test_audit_trail_created(self):
        coord = _build_coordinator()
        opp = _make_opportunity()
        await coord.execute_opportunity(opp)

        coord._audit.log_execution_created.assert_called_once()
        coord._audit.log_risk_check.assert_called_once()
        # At least 3 state transitions: CREATED->RISK_CHECKING->READY->EXECUTING
        assert coord._audit.log_state_transition.call_count >= 3

    @pytest.mark.asyncio
    async def test_inventory_refreshed_after_execution(self):
        coord = _build_coordinator()
        opp = _make_opportunity()
        await coord.execute_opportunity(opp)
        coord._inventory.refresh_all.assert_awaited_once()


class TestExecuteOpportunityRiskRejection:
    @pytest.mark.asyncio
    async def test_risk_rejected(self):
        opp = _make_opportunity()
        coord = _build_coordinator(plan_data=_rejected_plan_data(opp))
        result = await coord.execute_opportunity(opp)

        assert result.state == "RISK_REJECTED"
        assert "Risk rejected" in result.error_message

    @pytest.mark.asyncio
    async def test_engine_not_called_on_rejection(self):
        opp = _make_opportunity()
        coord = _build_coordinator(plan_data=_rejected_plan_data(opp))
        await coord.execute_opportunity(opp)

        coord._engine.execute.assert_not_awaited()


class TestExecuteOpportunityFailure:
    @pytest.mark.asyncio
    async def test_plan_build_failure(self):
        coord = _build_coordinator()
        coord._planner.build_cross_exchange_plan = AsyncMock(
            side_effect=RuntimeError("plan error")
        )
        opp = _make_opportunity()
        result = await coord.execute_opportunity(opp)

        assert result.state == "FAILED"
        assert "Plan build failed" in result.error_message


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

class TestQueries:
    @pytest.mark.asyncio
    async def test_get_active_executions_empty(self):
        coord = _build_coordinator()
        result = await coord.get_active_executions()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_execution_detail_not_found(self):
        coord = _build_coordinator()
        result = await coord.get_execution_detail("nonexistent")
        assert result is None
