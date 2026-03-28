"""
ExecutionCoordinator -- orchestrates the full execution lifecycle:
  opportunity -> plan -> risk check -> execute -> record -> inventory update -> audit

Wraps the lower-level :class:`ExecutionEngine` with state machine tracking,
risk gating, audit logging, alert generation, and analytics recording.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.events import EventBus, EventType
from app.core.state_machine import (
    StateMachine,
    InvalidStateTransition,
    create_execution_sm,
    create_leg_sm,
)
from app.services.alert_service import AlertCandidate, AlertService
from app.services.analytics import AnalyticsService
from app.services.audit import AuditService
from app.services.execution_engine import ExecutionEngine, ExecutionResult, LegResult
from app.services.execution_planner import ExecutionPlanData, ExecutionPlanner
from app.services.inventory import InventoryManager
from app.services.risk_engine import RiskEngine
from app.services.scanner import OpportunityCandidate


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ActiveExecution:
    """Tracks an in-flight execution."""
    execution_id: str
    state_machine: StateMachine
    plan: ExecutionPlanData
    started_at: datetime
    legs_status: dict[int, str] = field(default_factory=dict)
    leg_state_machines: dict[int, StateMachine] = field(default_factory=dict)
    result: ExecutionResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "state": self.state_machine.state,
            "strategy_type": self.plan.strategy_type,
            "mode": self.plan.mode,
            "started_at": self.started_at.isoformat(),
            "legs_status": self.legs_status,
            "is_terminal": self.state_machine.is_terminal,
            "plan_id": self.plan.plan_id,
            "target_notional_usdt": self.plan.target_notional_usdt,
            "planned_net_profit": self.plan.planned_net_profit,
        }


# ---------------------------------------------------------------------------
# ExecutionCoordinator
# ---------------------------------------------------------------------------

class ExecutionCoordinator:
    """Orchestrates the full execution lifecycle for arbitrage opportunities.

    Ties together planner, risk engine, execution engine, inventory manager,
    audit service, alert service, and analytics into a single coherent
    workflow.
    """

    def __init__(
        self,
        execution_engine: ExecutionEngine,
        risk_engine: RiskEngine,
        inventory_manager: InventoryManager,
        alert_service: AlertService,
        audit_service: AuditService,
        analytics_service: AnalyticsService,
        event_bus: EventBus,
        execution_planner: ExecutionPlanner,
    ) -> None:
        self._engine = execution_engine
        self._risk_engine = risk_engine
        self._inventory = inventory_manager
        self._alerts = alert_service
        self._audit = audit_service
        self._analytics = analytics_service
        self._event_bus = event_bus
        self._planner = execution_planner

        self._active_executions: dict[str, ActiveExecution] = {}

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    async def execute_opportunity(
        self,
        opportunity: OpportunityCandidate,
        mode: str = "PAPER",
    ) -> ExecutionResult:
        """Full lifecycle execution of an opportunity.

        Steps:
          1. Build plan via ExecutionPlanner
          2. Create state machine for execution
          3. Run pre-trade risk check (embedded in plan)
          4. If rejected, log and return
          5. Transition to EXECUTING
          6. Execute via ExecutionEngine (paper or live)
          7. Process result (success/partial/failed/hedging)
          8. Update inventory
          9. Record PnL
         10. Generate alerts if needed
         11. Write audit log
         12. Return result
        """
        execution_id = uuid.uuid4().hex

        # 1. Build plan
        try:
            if opportunity.strategy_type == "TRIANGULAR":
                plan = await self._planner.build_triangular_plan(opportunity, mode=mode)
            else:
                plan = await self._planner.build_cross_exchange_plan(opportunity, mode=mode)
        except Exception as exc:
            logger.opt(exception=True).error(
                "Failed to build plan for opportunity {}",
                opportunity.id,
            )
            result = ExecutionResult(
                execution_id=execution_id,
                opportunity_id=opportunity.id,
                strategy_type=opportunity.strategy_type,
                mode=mode,
                state="FAILED",
                error_message=f"Plan build failed: {exc}",
                started_at=time.time(),
                completed_at=time.time(),
            )
            self._audit.log(
                event_type="EXECUTION_FAILED",
                entity_type="execution",
                entity_id=execution_id,
                action="plan_build_failed",
                details={"error": str(exc), "opportunity_id": opportunity.id},
            )
            return result

        # 2. Create state machine
        sm = create_execution_sm(execution_id)

        # Create leg state machines
        leg_sms: dict[int, StateMachine] = {}
        legs_status: dict[int, str] = {}
        for leg in plan.legs:
            leg_id = f"{execution_id}:leg{leg.leg_index}"
            leg_sms[leg.leg_index] = create_leg_sm(leg_id)
            legs_status[leg.leg_index] = "PENDING"

        active = ActiveExecution(
            execution_id=execution_id,
            state_machine=sm,
            plan=plan,
            started_at=datetime.now(timezone.utc),
            legs_status=legs_status,
            leg_state_machines=leg_sms,
        )
        self._active_executions[execution_id] = active

        # Audit: execution created
        self._audit.log_execution_created(execution_id, plan.to_dict())

        # 3. Risk check (already performed during plan building)
        sm.transition("RISK_CHECKING", reason="evaluating risk rules")
        self._audit.log_state_transition(
            "execution", execution_id, "CREATED", "RISK_CHECKING",
        )

        risk_result_dict = {
            "approved": plan.risk_check.approved,
            "violations": [
                {"rule": v.rule_name, "reason": v.reason}
                for v in plan.risk_check.violations
            ],
            "rule_count": len(plan.risk_check.results),
        }
        self._audit.log_risk_check(execution_id, risk_result_dict)

        # 4. If rejected, log and return
        if not plan.risk_check.approved:
            sm.transition("RISK_REJECTED", reason="risk check failed")
            self._audit.log_state_transition(
                "execution", execution_id,
                "RISK_CHECKING", "RISK_REJECTED",
                reason=f"violations: {plan.risk_check.violation_names}",
            )

            # Clean up
            self._active_executions.pop(execution_id, None)

            result = ExecutionResult(
                execution_id=execution_id,
                opportunity_id=opportunity.id,
                strategy_type=opportunity.strategy_type,
                mode=mode,
                state="RISK_REJECTED",
                planned_profit_pct=opportunity.estimated_net_profit_pct,
                error_message=f"Risk rejected: {plan.risk_check.violation_names}",
                started_at=time.time(),
                completed_at=time.time(),
            )

            logger.warning(
                "Execution {} rejected by risk engine: {}",
                execution_id, plan.risk_check.violation_names,
            )
            return result

        # 5. Transition to READY then EXECUTING
        sm.transition("READY", reason="risk check passed")
        self._audit.log_state_transition(
            "execution", execution_id, "RISK_CHECKING", "READY",
        )

        sm.transition("EXECUTING", reason="starting execution")
        self._audit.log_state_transition(
            "execution", execution_id, "READY", "EXECUTING",
        )

        # Audit leg submissions
        for leg in plan.legs:
            self._audit.log_leg_submitted(
                execution_id=execution_id,
                leg_index=leg.leg_index,
                exchange=leg.exchange,
                symbol=leg.symbol,
                side=leg.side,
            )
            leg_sm = leg_sms.get(leg.leg_index)
            if leg_sm:
                leg_sm.transition("SUBMITTING", reason="order being placed")

        # 6. Execute via engine
        try:
            result = await self._engine.execute(opportunity, mode=mode)
            result.execution_id = execution_id
        except Exception as exc:
            logger.opt(exception=True).error(
                "ExecutionEngine raised for {}",
                execution_id,
            )
            result = ExecutionResult(
                execution_id=execution_id,
                opportunity_id=opportunity.id,
                strategy_type=opportunity.strategy_type,
                mode=mode,
                state="FAILED",
                error_message=f"Engine error: {exc}",
                started_at=time.time(),
                completed_at=time.time(),
            )

        # 7. Process result -- update execution state machine
        active.result = result
        await self._process_execution_result(active, result)

        # 8. Update inventory (trigger a refresh)
        try:
            await self._inventory.refresh_all()
        except Exception:
            logger.opt(exception=True).warning(
                "Inventory refresh after execution {} failed",
                execution_id,
            )

        # 9. PnL is already recorded by the execution engine's _persist_execution
        # Log it in audit for traceability
        if result.success:
            self._audit.log(
                event_type="PNL_RECORDED",
                entity_type="execution",
                entity_id=execution_id,
                action="pnl_recorded",
                details={
                    "gross_profit_usdt": result.gross_profit_usdt,
                    "total_fees_usdt": result.total_fees_usdt,
                    "net_profit_usdt": result.actual_profit_usdt,
                    "net_profit_pct": result.actual_profit_pct,
                    "execution_time_ms": result.execution_time_ms,
                },
            )

        # 10. Generate alerts if needed
        await self._check_post_execution_alerts(execution_id, result)

        # 11. Final audit entry
        self._audit.log(
            event_type="EXECUTION_COMPLETED" if result.success else "EXECUTION_FAILED",
            entity_type="execution",
            entity_id=execution_id,
            action="completed" if result.success else "failed",
            details={
                "state": result.state,
                "profit_usdt": result.actual_profit_usdt,
                "execution_time_ms": result.execution_time_ms,
                "error": result.error_message or "",
                "leg_count": len(result.legs),
            },
        )

        # Clean up active executions if terminal
        if sm.is_terminal:
            self._active_executions.pop(execution_id, None)

        logger.info(
            "Coordinator finished execution {}: state={} profit={:.4f} USDT",
            execution_id, result.state, result.actual_profit_usdt,
        )

        return result

    # ------------------------------------------------------------------
    # Direct execution methods
    # ------------------------------------------------------------------

    async def execute_cross_exchange(
        self,
        symbol: str,
        buy_exchange: str,
        sell_exchange: str,
        quantity: float | None = None,
        mode: str = "PAPER",
    ) -> ExecutionResult:
        """Direct cross-exchange execution without a pre-existing opportunity.

        Constructs a synthetic :class:`OpportunityCandidate` from the given
        parameters and delegates to :meth:`execute_opportunity`.
        """
        # Build a synthetic opportunity from parameters
        buy_ticker = self._planner._market_data.get_ticker(buy_exchange, symbol)
        sell_ticker = self._planner._market_data.get_ticker(sell_exchange, symbol)

        buy_price = buy_ticker.ask if buy_ticker else 0.0
        sell_price = sell_ticker.bid if sell_ticker else 0.0

        if buy_price <= 0 or sell_price <= 0:
            return ExecutionResult(
                state="FAILED",
                error_message=f"No valid ticker data for {symbol} on {buy_exchange}/{sell_exchange}",
                started_at=time.time(),
                completed_at=time.time(),
            )

        spread_pct = (sell_price - buy_price) / buy_price * 100.0

        # Determine quantity
        if quantity is None or quantity <= 0:
            # Use a conservative default based on available balance
            bal = self._inventory.get_balance(buy_exchange, symbol.split("/")[1] if "/" in symbol else "USDT")
            if bal and buy_price > 0:
                quantity = bal.free * 0.1 / buy_price  # 10% of available
            else:
                quantity = 0.001  # minimal default

        opp = OpportunityCandidate(
            strategy_type="CROSS_EXCHANGE",
            symbol=symbol,
            symbols=[symbol],
            exchanges=[buy_exchange, sell_exchange],
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_pct=spread_pct,
            theoretical_profit_pct=spread_pct,
            estimated_net_profit_pct=spread_pct - 0.2,  # rough fee estimate
            estimated_slippage_pct=0.05,
            executable_quantity=quantity,
            executable_value_usdt=quantity * buy_price,
            buy_fee_pct=0.1,
            sell_fee_pct=0.1,
        )

        return await self.execute_opportunity(opp, mode=mode)

    async def execute_triangular(
        self,
        exchange: str,
        path: list[str],
        start_amount: float = 1000.0,
        mode: str = "PAPER",
    ) -> ExecutionResult:
        """Direct triangular execution.

        Args:
            exchange: the exchange to trade on
            path: list of 3 symbols, e.g. ["BTC/USDT", "ETH/BTC", "ETH/USDT"]
            start_amount: starting notional in the quote asset of the first pair
            mode: "PAPER" or "LIVE"
        """
        if len(path) != 3:
            return ExecutionResult(
                state="FAILED",
                error_message=f"Triangular requires 3 symbols, got {len(path)}",
                started_at=time.time(),
                completed_at=time.time(),
            )

        # Build synthetic opportunity
        md = self._planner._market_data
        t1 = md.get_ticker(exchange, path[0])
        t2 = md.get_ticker(exchange, path[1])
        t3 = md.get_ticker(exchange, path[2])

        if not t1 or not t2 or not t3:
            missing = []
            if not t1:
                missing.append(path[0])
            if not t2:
                missing.append(path[1])
            if not t3:
                missing.append(path[2])
            return ExecutionResult(
                state="FAILED",
                error_message=f"Missing ticker data for: {missing}",
                started_at=time.time(),
                completed_at=time.time(),
            )

        # Rough profit estimation
        p1, p2, p3 = t1.ask, t2.ask, t3.bid
        if p1 > 0 and p2 > 0 and p3 > 0:
            implied = (1.0 / p1) * (1.0 / p2) * p3
            theoretical_pct = (implied - 1.0) * 100.0
        else:
            theoretical_pct = 0.0

        opp = OpportunityCandidate(
            strategy_type="TRIANGULAR",
            symbol=">".join(path),
            symbols=path,
            exchanges=[exchange],
            buy_exchange=exchange,
            sell_exchange=exchange,
            buy_price=p1,
            sell_price=p3,
            spread_pct=theoretical_pct,
            theoretical_profit_pct=theoretical_pct,
            estimated_net_profit_pct=theoretical_pct - 0.3,  # 3 legs of fees
            executable_quantity=start_amount / p1 if p1 > 0 else 0.0,
            executable_value_usdt=start_amount,
            buy_fee_pct=0.3,  # total for 3 legs
        )

        return await self.execute_opportunity(opp, mode=mode)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_active_executions(self) -> list[dict[str, Any]]:
        """Return a summary of all currently in-flight executions."""
        return [active.to_dict() for active in self._active_executions.values()]

    async def get_execution_detail(
        self,
        execution_id: str,
    ) -> dict[str, Any] | None:
        """Return detailed information about an execution (active or recent)."""
        active = self._active_executions.get(execution_id)
        if active is None:
            return None

        detail = active.to_dict()
        detail["plan"] = active.plan.to_dict()
        detail["state_history"] = [
            {
                "from": t.from_state,
                "to": t.to_state,
                "timestamp": t.timestamp.isoformat(),
                "reason": t.reason,
            }
            for t in active.state_machine.history
        ]
        detail["audit_trail"] = [
            e.to_dict()
            for e in self._audit.get_entries_for_execution(execution_id)
        ]

        if active.result is not None:
            detail["result"] = active.result.to_dict()

        return detail

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_execution_result(
        self,
        active: ActiveExecution,
        result: ExecutionResult,
    ) -> None:
        """Map the engine result state onto the execution state machine."""
        sm = active.state_machine
        exec_id = active.execution_id

        # Update leg state machines and statuses based on result
        for leg_result in result.legs:
            idx = leg_result.leg_index
            leg_sm = active.leg_state_machines.get(idx)

            if leg_result.status == "FILLED":
                active.legs_status[idx] = "FILLED"
                if leg_sm and leg_sm.can_transition("SUBMITTED"):
                    leg_sm.transition("SUBMITTED", reason="order acknowledged")
                if leg_sm and leg_sm.can_transition("FILLED"):
                    leg_sm.transition("FILLED", reason="order filled")
                self._audit.log_leg_filled(
                    execution_id=exec_id,
                    leg_index=idx,
                    fill_price=leg_result.actual_price,
                    fill_qty=leg_result.actual_quantity,
                )
            elif leg_result.status == "PARTIAL_FILLED":
                active.legs_status[idx] = "PARTIAL_FILLED"
                if leg_sm and leg_sm.can_transition("SUBMITTED"):
                    leg_sm.transition("SUBMITTED", reason="order acknowledged")
                if leg_sm and leg_sm.can_transition("PARTIAL_FILLED"):
                    leg_sm.transition("PARTIAL_FILLED", reason="partially filled")
            elif leg_result.status == "FAILED":
                active.legs_status[idx] = "FAILED"
                if leg_sm and leg_sm.can_transition("SUBMITTED"):
                    leg_sm.transition("SUBMITTED", reason="order acknowledged")
                if leg_sm and leg_sm.can_transition("FAILED"):
                    leg_sm.transition("FAILED", reason=leg_result.error or "unknown error")
            elif leg_result.status in ("CANCELED", "CANCELLED"):
                active.legs_status[idx] = "CANCELLED"
                if leg_sm and leg_sm.can_transition("CANCELLED"):
                    leg_sm.transition("CANCELLED", reason="order cancelled")
                elif leg_sm and leg_sm.can_transition("SUBMITTED"):
                    leg_sm.transition("SUBMITTED", reason="order acknowledged")
                    if leg_sm.can_transition("CANCELLED"):
                        leg_sm.transition("CANCELLED", reason="order cancelled")

        # Map engine state to execution SM state
        engine_state = result.state
        try:
            if engine_state in ("COMPLETED", "FILLED"):
                if sm.can_transition("COMPLETED"):
                    sm.transition(
                        "COMPLETED",
                        reason=f"all legs done, profit={result.actual_profit_usdt:.4f} USDT",
                    )
                    self._audit.log_state_transition(
                        "execution", exec_id, "EXECUTING", "COMPLETED",
                    )
            elif engine_state == "PARTIAL_FILLED":
                if sm.can_transition("PARTIALLY_FILLED"):
                    sm.transition("PARTIALLY_FILLED", reason="some legs partially filled")
                    self._audit.log_state_transition(
                        "execution", exec_id, "EXECUTING", "PARTIALLY_FILLED",
                    )
                # Partial fills that were subsequently hedged end up COMPLETED
                if result.state == "COMPLETED" and sm.can_transition("COMPLETED"):
                    sm.transition("COMPLETED", reason="partial fill hedged and completed")
            elif engine_state == "HEDGING":
                if sm.can_transition("HEDGING"):
                    sm.transition("HEDGING", reason="hedging single-leg failure")
                    self._audit.log_state_transition(
                        "execution", exec_id, "EXECUTING", "HEDGING",
                    )
                # If the hedge itself resolved to COMPLETED
                if sm.can_transition("COMPLETED"):
                    sm.transition("COMPLETED", reason="hedge completed")
                elif sm.can_transition("FAILED"):
                    sm.transition("FAILED", reason="hedge failed")
            elif engine_state == "FAILED":
                if sm.can_transition("FAILED"):
                    sm.transition(
                        "FAILED",
                        reason=result.error_message or "execution failed",
                    )
                    self._audit.log_state_transition(
                        "execution", exec_id, "EXECUTING", "FAILED",
                    )
            else:
                # Unknown or already-terminal state -- try to fail gracefully
                if sm.can_transition("FAILED"):
                    sm.transition("FAILED", reason=f"unexpected engine state: {engine_state}")
        except InvalidStateTransition:
            logger.opt(exception=True).warning(
                "State machine transition conflict for execution {}",
                exec_id,
            )

    async def _check_post_execution_alerts(
        self,
        execution_id: str,
        result: ExecutionResult,
    ) -> None:
        """Generate alerts for notable execution outcomes."""
        # Alert on execution failure
        if result.state == "FAILED" and result.error_message:
            await self._alerts.send_alert(AlertCandidate(
                alert_type="EXECUTION_FAILED",
                severity="WARNING",
                title=f"Execution failed: {execution_id[:12]}",
                message=f"Execution {execution_id} failed: {result.error_message}",
                source="execution_coordinator",
                details={
                    "execution_id": execution_id,
                    "strategy_type": result.strategy_type,
                    "mode": result.mode,
                    "error": result.error_message,
                },
            ))
            self._audit.log_alert_generated(
                alert_id=execution_id,
                alert_type="EXECUTION_FAILED",
                severity="WARNING",
                message=result.error_message,
            )

        # Alert on hedging events (indicates one-sided execution risk)
        if result.state == "HEDGING" or any(
            "hedge" in (leg.error or "").lower() for leg in result.legs
        ):
            await self._alerts.send_alert(AlertCandidate(
                alert_type="EXECUTION_HEDGING",
                severity="CRITICAL",
                title=f"Hedging required: {execution_id[:12]}",
                message=(
                    f"Execution {execution_id} required hedging. "
                    f"This indicates a single-leg failure that needed emergency reversal."
                ),
                source="execution_coordinator",
                details={
                    "execution_id": execution_id,
                    "legs": [
                        {"index": l.leg_index, "status": l.status, "error": l.error}
                        for l in result.legs
                    ],
                },
            ))

        # Alert on significant negative PnL
        if result.actual_profit_usdt < -10.0:
            await self._alerts.send_alert(AlertCandidate(
                alert_type="NEGATIVE_PNL",
                severity="WARNING",
                title=f"Negative PnL: ${result.actual_profit_usdt:.2f}",
                message=(
                    f"Execution {execution_id} resulted in significant loss: "
                    f"${result.actual_profit_usdt:.2f} USDT"
                ),
                source="execution_coordinator",
                details={
                    "execution_id": execution_id,
                    "net_profit_usdt": result.actual_profit_usdt,
                    "gross_profit_usdt": result.gross_profit_usdt,
                    "fees_usdt": result.total_fees_usdt,
                },
            ))

        # Alert on high slippage
        if result.total_slippage_usdt > 5.0:
            await self._alerts.send_alert(AlertCandidate(
                alert_type="HIGH_SLIPPAGE",
                severity="WARNING",
                title=f"High slippage: ${result.total_slippage_usdt:.2f}",
                message=(
                    f"Execution {execution_id} experienced slippage of "
                    f"${result.total_slippage_usdt:.2f} USDT"
                ),
                source="execution_coordinator",
                details={
                    "execution_id": execution_id,
                    "total_slippage_usdt": result.total_slippage_usdt,
                    "per_leg": [
                        {"index": l.leg_index, "slippage_pct": l.slippage_pct}
                        for l in result.legs
                    ],
                },
            ))
