"""
ExecutionEngine -- orchestrates the actual placement of arbitrage orders
across exchanges, with state machine tracking and failure handling.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum, auto
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.db.redis import RedisClient
from app.exchanges.base import (
    BaseExchangeAdapter,
    OrderSide,
    OrderType,
    StandardOrder,
)
from app.exchanges.factory import ExchangeFactory
from app.models.analytics import PnlRecord
from app.models.execution import (
    ExecutionLeg,
    ExecutionMode,
    ExecutionPlan,
    ExecutionPlanStatus,
    LegSide,
    LegStatus,
)
from app.models.opportunity import StrategyType
from app.services.risk_engine import RiskEngine
from app.services.scanner import OpportunityCandidate
from app.services.simulation import SimulationService


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ExecutionState(StrEnum):
    PENDING = auto()
    SUBMITTING = auto()
    PARTIAL_FILLED = auto()
    FILLED = auto()
    COMPLETED = auto()
    FAILED = auto()
    HEDGING = auto()


@dataclass(slots=True)
class LegResult:
    """Outcome of a single execution leg."""
    leg_index: int
    exchange: str
    symbol: str
    side: str
    planned_price: float
    planned_quantity: float
    actual_price: float = 0.0
    actual_quantity: float = 0.0
    fee: float = 0.0
    fee_asset: str = ""
    slippage_pct: float = 0.0
    order_id: str = ""
    exchange_order_id: str = ""
    status: str = "PENDING"
    error: str = ""
    submitted_at: float = 0.0
    filled_at: float = 0.0


@dataclass(slots=True)
class ExecutionResult:
    """Full outcome of an arbitrage execution."""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    opportunity_id: str = ""
    strategy_type: str = "CROSS_EXCHANGE"
    mode: str = "PAPER"
    state: str = "PENDING"
    legs: list[LegResult] = field(default_factory=list)
    planned_profit_pct: float = 0.0
    actual_profit_pct: float = 0.0
    actual_profit_usdt: float = 0.0
    gross_profit_usdt: float = 0.0
    total_fees_usdt: float = 0.0
    total_slippage_usdt: float = 0.0
    execution_time_ms: float = 0.0
    error_message: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def success(self) -> bool:
        return self.state in ("COMPLETED", "FILLED")

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "opportunity_id": self.opportunity_id,
            "strategy_type": self.strategy_type,
            "mode": self.mode,
            "state": self.state,
            "planned_profit_pct": self.planned_profit_pct,
            "actual_profit_pct": self.actual_profit_pct,
            "actual_profit_usdt": self.actual_profit_usdt,
            "total_fees_usdt": self.total_fees_usdt,
            "execution_time_ms": self.execution_time_ms,
            "legs": len(self.legs),
            "error_message": self.error_message,
        }


# ---------------------------------------------------------------------------
# ExecutionEngine
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """Orchestrates arbitrage order execution across exchanges.

    Supports cross-exchange (2-leg parallel) and triangular (3-leg sequential)
    strategies, with paper-mode delegation to SimulationService.
    """

    def __init__(
        self,
        event_bus: EventBus,
        exchange_factory: ExchangeFactory,
        redis_client: RedisClient,
        session_factory: async_sessionmaker[AsyncSession],
        risk_engine: RiskEngine,
        simulation_service: SimulationService,
        config: Settings | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._exchange_factory = exchange_factory
        self._redis = redis_client
        self._session_factory = session_factory
        self._risk_engine = risk_engine
        self._simulation = simulation_service
        self._cfg = config or settings

        self._execution_timeout_s = self._cfg.strategy.execution_timeout_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        opportunity: OpportunityCandidate,
        mode: str = "PAPER",
    ) -> ExecutionResult:
        """Execute an arbitrage opportunity.

        If *mode* is ``"PAPER"``, delegates to the simulation service.
        Otherwise places real orders on the exchanges.
        """
        result = ExecutionResult(
            opportunity_id=opportunity.id,
            strategy_type=opportunity.strategy_type,
            mode=mode,
            planned_profit_pct=opportunity.estimated_net_profit_pct,
            started_at=time.time(),
        )

        await self._event_bus.publish(
            EventType.EXECUTION_STARTED,
            {
                "execution_id": result.execution_id,
                "opportunity_id": opportunity.id,
                "strategy_type": opportunity.strategy_type,
                "mode": mode,
            },
        )

        await self._risk_engine.increment_concurrent()

        try:
            if mode == "PAPER":
                result = await self._execute_paper(opportunity, result)
            elif opportunity.strategy_type == "CROSS_EXCHANGE":
                result = await self._execute_cross_exchange(opportunity, result)
            elif opportunity.strategy_type == "TRIANGULAR":
                result = await self._execute_triangular(opportunity, result)
            else:
                result.state = "FAILED"
                result.error_message = f"Unknown strategy type: {opportunity.strategy_type}"
        except Exception as exc:
            logger.opt(exception=True).error("Execution failed for {}", opportunity.id)
            result.state = "FAILED"
            result.error_message = str(exc)

        result.completed_at = time.time()
        result.execution_time_ms = (result.completed_at - result.started_at) * 1000.0

        await self._risk_engine.decrement_concurrent()
        await self._risk_engine.record_execution_result(result.success)

        if result.success:
            await self._risk_engine.record_daily_pnl(result.actual_profit_usdt)

        # Persist to DB
        await self._persist_execution(opportunity, result)

        # Publish completion event
        event_type = EventType.EXECUTION_COMPLETED if result.success else EventType.EXECUTION_FAILED
        await self._event_bus.publish(event_type, result.to_dict())

        logger.info(
            "Execution {}: state={} profit={:.4f} USDT time={:.0f}ms",
            result.execution_id, result.state,
            result.actual_profit_usdt, result.execution_time_ms,
        )

        return result

    # ------------------------------------------------------------------
    # Paper mode
    # ------------------------------------------------------------------

    async def _execute_paper(
        self,
        opportunity: OpportunityCandidate,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """Delegate execution to the simulation service."""
        if opportunity.strategy_type == "CROSS_EXCHANGE":
            sim_result = await self._simulation.simulate_cross_exchange(opportunity)
        else:
            sim_result = await self._simulation.simulate_triangular(opportunity)

        result.state = "COMPLETED"
        result.actual_profit_usdt = sim_result.net_profit_usdt
        result.gross_profit_usdt = sim_result.gross_profit_usdt
        result.total_fees_usdt = sim_result.total_fees_usdt
        result.total_slippage_usdt = sim_result.total_slippage_usdt
        if sim_result.entry_value_usdt > 0:
            result.actual_profit_pct = (
                sim_result.net_profit_usdt / sim_result.entry_value_usdt * 100.0
            )

        # Build leg results from simulation
        for i, leg_sim in enumerate(sim_result.legs):
            result.legs.append(LegResult(
                leg_index=i,
                exchange=leg_sim.exchange,
                symbol=leg_sim.symbol,
                side=leg_sim.side,
                planned_price=leg_sim.planned_price,
                planned_quantity=leg_sim.planned_quantity,
                actual_price=leg_sim.fill_price,
                actual_quantity=leg_sim.fill_quantity,
                fee=leg_sim.fee_usdt,
                fee_asset="USDT",
                slippage_pct=leg_sim.slippage_pct,
                status="FILLED",
                filled_at=time.time(),
            ))

        return result

    # ------------------------------------------------------------------
    # Cross-exchange (live)
    # ------------------------------------------------------------------

    async def _execute_cross_exchange(
        self,
        opportunity: OpportunityCandidate,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """Place simultaneous buy/sell on different exchanges."""
        result.state = "SUBMITTING"

        buy_adapter = self._exchange_factory.get(opportunity.buy_exchange)
        sell_adapter = self._exchange_factory.get(opportunity.sell_exchange)
        symbol = opportunity.symbols[0] if opportunity.symbols else opportunity.symbol
        quantity = opportunity.executable_quantity

        buy_leg = LegResult(
            leg_index=0,
            exchange=opportunity.buy_exchange,
            symbol=symbol,
            side="BUY",
            planned_price=opportunity.buy_price,
            planned_quantity=quantity,
        )
        sell_leg = LegResult(
            leg_index=1,
            exchange=opportunity.sell_exchange,
            symbol=symbol,
            side="SELL",
            planned_price=opportunity.sell_price,
            planned_quantity=quantity,
        )
        result.legs = [buy_leg, sell_leg]

        # Place both orders simultaneously
        async def _place_buy() -> StandardOrder | None:
            buy_leg.submitted_at = time.time()
            try:
                order = await asyncio.wait_for(
                    buy_adapter.place_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                    ),
                    timeout=self._execution_timeout_s,
                )
                buy_leg.exchange_order_id = order.order_id
                buy_leg.actual_price = order.avg_fill_price or order.price or 0.0
                buy_leg.actual_quantity = order.filled_quantity
                buy_leg.fee = order.fee
                buy_leg.fee_asset = order.fee_asset
                buy_leg.filled_at = time.time()

                if order.status.value == "FILLED":
                    buy_leg.status = "FILLED"
                elif order.status.value == "PARTIALLY_FILLED":
                    buy_leg.status = "PARTIAL_FILLED"
                else:
                    buy_leg.status = "FAILED"
                    buy_leg.error = f"Unexpected order status: {order.status.value}"

                return order
            except asyncio.TimeoutError:
                buy_leg.status = "FAILED"
                buy_leg.error = "Order timed out"
                return None
            except Exception as exc:
                buy_leg.status = "FAILED"
                buy_leg.error = str(exc)
                return None

        async def _place_sell() -> StandardOrder | None:
            sell_leg.submitted_at = time.time()
            try:
                order = await asyncio.wait_for(
                    sell_adapter.place_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                    ),
                    timeout=self._execution_timeout_s,
                )
                sell_leg.exchange_order_id = order.order_id
                sell_leg.actual_price = order.avg_fill_price or order.price or 0.0
                sell_leg.actual_quantity = order.filled_quantity
                sell_leg.fee = order.fee
                sell_leg.fee_asset = order.fee_asset
                sell_leg.filled_at = time.time()

                if order.status.value == "FILLED":
                    sell_leg.status = "FILLED"
                elif order.status.value == "PARTIALLY_FILLED":
                    sell_leg.status = "PARTIAL_FILLED"
                else:
                    sell_leg.status = "FAILED"
                    sell_leg.error = f"Unexpected order status: {order.status.value}"

                return order
            except asyncio.TimeoutError:
                sell_leg.status = "FAILED"
                sell_leg.error = "Order timed out"
                return None
            except Exception as exc:
                sell_leg.status = "FAILED"
                sell_leg.error = str(exc)
                return None

        buy_order, sell_order = await asyncio.gather(
            _place_buy(), _place_sell(), return_exceptions=False,
        )

        # Determine aggregate state
        both_filled = buy_leg.status == "FILLED" and sell_leg.status == "FILLED"
        any_partial = buy_leg.status == "PARTIAL_FILLED" or sell_leg.status == "PARTIAL_FILLED"
        buy_failed = buy_leg.status == "FAILED"
        sell_failed = sell_leg.status == "FAILED"

        if both_filled:
            result.state = "COMPLETED"
            result = self._compute_pnl(result, opportunity)
        elif any_partial:
            result.state = "PARTIAL_FILLED"
            # Attempt to handle partial fills
            result = await self._handle_partial_fill(result, opportunity, buy_adapter, sell_adapter)
        elif buy_failed and sell_failed:
            result.state = "FAILED"
            result.error_message = f"Both legs failed: buy={buy_leg.error}, sell={sell_leg.error}"
        elif buy_failed and not sell_failed:
            # Sell side filled but buy side failed -- need to hedge
            result.state = "HEDGING"
            result = await self._hedge_single_leg(result, sell_adapter, symbol, "BUY", sell_leg.actual_quantity)
        elif sell_failed and not buy_failed:
            # Buy side filled but sell side failed -- need to hedge
            result.state = "HEDGING"
            result = await self._hedge_single_leg(result, buy_adapter, symbol, "SELL", buy_leg.actual_quantity)

        return result

    # ------------------------------------------------------------------
    # Triangular (live)
    # ------------------------------------------------------------------

    async def _execute_triangular(
        self,
        opportunity: OpportunityCandidate,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """Execute 3 sequential legs on a single exchange."""
        result.state = "SUBMITTING"

        exchange_name = opportunity.exchanges[0] if opportunity.exchanges else ""
        adapter = self._exchange_factory.get(exchange_name)

        # Parse symbols from the opportunity
        symbols = opportunity.symbols
        if len(symbols) != 3:
            result.state = "FAILED"
            result.error_message = f"Triangular requires 3 symbols, got {len(symbols)}"
            return result

        # Determine starting quantity -- use a fraction of balance for safety
        # For now, use a fixed small amount or the calculated quantity
        quantity = opportunity.executable_quantity if opportunity.executable_quantity > 0 else 0.001

        legs_to_execute = []
        # Parse the opportunity symbol path for side info
        # The symbol field is like "BTC/USDT>ETH/BTC>ETH/USDT"
        opp_symbol = opportunity.symbol
        path_parts = opp_symbol.split(">") if ">" in opp_symbol else symbols

        # We need to determine the side for each leg based on the path
        # Simplified: alternate buy/sell based on typical triangular pattern
        sides = ["BUY", "BUY", "SELL"]  # Typical: buy A with base, buy B with A, sell B for base
        current_quantity = quantity

        for i, sym in enumerate(symbols):
            leg = LegResult(
                leg_index=i,
                exchange=exchange_name,
                symbol=sym,
                side=sides[i] if i < len(sides) else "BUY",
                planned_price=0.0,
                planned_quantity=current_quantity,
            )
            legs_to_execute.append(leg)

        result.legs = legs_to_execute

        # Execute legs sequentially
        for i, leg in enumerate(legs_to_execute):
            leg.submitted_at = time.time()
            try:
                side = OrderSide.BUY if leg.side == "BUY" else OrderSide.SELL
                order = await asyncio.wait_for(
                    adapter.place_order(
                        symbol=leg.symbol,
                        side=side,
                        order_type=OrderType.MARKET,
                        quantity=leg.planned_quantity,
                    ),
                    timeout=self._execution_timeout_s,
                )
                leg.exchange_order_id = order.order_id
                leg.actual_price = order.avg_fill_price or order.price or 0.0
                leg.actual_quantity = order.filled_quantity
                leg.fee = order.fee
                leg.fee_asset = order.fee_asset
                leg.filled_at = time.time()

                if order.status.value in ("FILLED", "PARTIALLY_FILLED"):
                    leg.status = "FILLED"
                    # Update quantity for next leg
                    if i < len(legs_to_execute) - 1:
                        # Output of this leg is input of next
                        if leg.side == "BUY":
                            legs_to_execute[i + 1].planned_quantity = leg.actual_quantity
                        else:
                            legs_to_execute[i + 1].planned_quantity = (
                                leg.actual_quantity * leg.actual_price
                            )
                else:
                    leg.status = "FAILED"
                    leg.error = f"Order status: {order.status.value}"
                    # Abort remaining legs
                    result.state = "FAILED"
                    result.error_message = f"Leg {i} failed: {leg.error}"
                    # Mark remaining legs as canceled
                    for remaining in legs_to_execute[i + 1:]:
                        remaining.status = "CANCELED"
                    return result

            except asyncio.TimeoutError:
                leg.status = "FAILED"
                leg.error = "Order timed out"
                result.state = "FAILED"
                result.error_message = f"Leg {i} timed out"
                for remaining in legs_to_execute[i + 1:]:
                    remaining.status = "CANCELED"
                return result
            except Exception as exc:
                leg.status = "FAILED"
                leg.error = str(exc)
                result.state = "FAILED"
                result.error_message = f"Leg {i} error: {exc}"
                for remaining in legs_to_execute[i + 1:]:
                    remaining.status = "CANCELED"
                return result

        # All legs filled
        result.state = "COMPLETED"
        result = self._compute_pnl(result, opportunity)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_pnl(
        self,
        result: ExecutionResult,
        opportunity: OpportunityCandidate,
    ) -> ExecutionResult:
        """Calculate PnL from actual leg results."""
        if opportunity.strategy_type == "CROSS_EXCHANGE" and len(result.legs) == 2:
            buy_leg = result.legs[0]
            sell_leg = result.legs[1]
            filled_qty = min(buy_leg.actual_quantity, sell_leg.actual_quantity)
            if filled_qty > 0 and buy_leg.actual_price > 0 and sell_leg.actual_price > 0:
                buy_cost = filled_qty * buy_leg.actual_price
                sell_revenue = filled_qty * sell_leg.actual_price
                gross = sell_revenue - buy_cost
                fees = buy_leg.fee + sell_leg.fee
                net = gross - fees

                result.gross_profit_usdt = gross
                result.total_fees_usdt = fees
                result.actual_profit_usdt = net
                result.total_slippage_usdt = (
                    abs(buy_leg.actual_price - buy_leg.planned_price) * filled_qty
                    + abs(sell_leg.planned_price - sell_leg.actual_price) * filled_qty
                )
                if buy_cost > 0:
                    result.actual_profit_pct = net / buy_cost * 100.0
                    # Compute per-leg slippage
                    if buy_leg.planned_price > 0:
                        buy_leg.slippage_pct = (
                            (buy_leg.actual_price - buy_leg.planned_price)
                            / buy_leg.planned_price * 100.0
                        )
                    if sell_leg.planned_price > 0:
                        sell_leg.slippage_pct = (
                            (sell_leg.planned_price - sell_leg.actual_price)
                            / sell_leg.planned_price * 100.0
                        )
        elif opportunity.strategy_type == "TRIANGULAR" and len(result.legs) >= 3:
            # For triangular, profit is the difference between what we started with and ended with
            first_leg = result.legs[0]
            last_leg = result.legs[-1]
            # Rough PnL: last leg output minus first leg input
            input_value = first_leg.planned_quantity * first_leg.actual_price if first_leg.actual_price > 0 else 0
            output_value = last_leg.actual_quantity * last_leg.actual_price if last_leg.actual_price > 0 else 0
            fees = sum(l.fee for l in result.legs)
            gross = output_value - input_value
            net = gross - fees
            result.gross_profit_usdt = gross
            result.total_fees_usdt = fees
            result.actual_profit_usdt = net
            if input_value > 0:
                result.actual_profit_pct = net / input_value * 100.0

        return result

    async def _handle_partial_fill(
        self,
        result: ExecutionResult,
        opportunity: OpportunityCandidate,
        buy_adapter: BaseExchangeAdapter,
        sell_adapter: BaseExchangeAdapter,
    ) -> ExecutionResult:
        """Handle partial fill by adjusting the other side."""
        buy_leg = result.legs[0]
        sell_leg = result.legs[1]

        # Determine the minimum filled quantity
        buy_filled = buy_leg.actual_quantity if buy_leg.status in ("FILLED", "PARTIAL_FILLED") else 0.0
        sell_filled = sell_leg.actual_quantity if sell_leg.status in ("FILLED", "PARTIAL_FILLED") else 0.0

        if buy_filled > sell_filled and sell_filled > 0:
            # Buy filled more than sell -- try to sell the excess
            excess = buy_filled - sell_filled
            if excess > 0:
                try:
                    symbol = opportunity.symbols[0]
                    await buy_adapter.place_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=excess,
                    )
                    logger.info("Hedged excess buy of {:.8f} on {}", excess, buy_leg.exchange)
                except Exception as exc:
                    logger.error("Failed to hedge excess buy: {}", exc)
        elif sell_filled > buy_filled and buy_filled > 0:
            excess = sell_filled - buy_filled
            if excess > 0:
                try:
                    symbol = opportunity.symbols[0]
                    await sell_adapter.place_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=excess,
                    )
                    logger.info("Hedged excess sell of {:.8f} on {}", excess, sell_leg.exchange)
                except Exception as exc:
                    logger.error("Failed to hedge excess sell: {}", exc)

        result.state = "COMPLETED"
        result = self._compute_pnl(result, opportunity)
        return result

    async def _hedge_single_leg(
        self,
        result: ExecutionResult,
        adapter: BaseExchangeAdapter,
        symbol: str,
        hedge_side: str,
        quantity: float,
    ) -> ExecutionResult:
        """Emergency hedge: reverse a filled leg when the other side failed."""
        logger.warning(
            "HEDGING: placing {} {} {:.8f} on {}",
            hedge_side, symbol, quantity, adapter.name,
        )
        try:
            side = OrderSide.BUY if hedge_side == "BUY" else OrderSide.SELL
            order = await asyncio.wait_for(
                adapter.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                ),
                timeout=self._execution_timeout_s,
            )
            if order.status.value in ("FILLED", "PARTIALLY_FILLED"):
                result.state = "COMPLETED"
                result.error_message = f"Hedged after single-leg failure: {hedge_side} {quantity}"
                logger.info("Hedge successful")
            else:
                result.state = "FAILED"
                result.error_message = f"Hedge order status: {order.status.value}"
                logger.error("Hedge order not filled: {}", order.status.value)
        except Exception as exc:
            result.state = "FAILED"
            result.error_message = f"Hedge failed: {exc}"
            logger.error("Hedge failed: {}", exc)

        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_execution(
        self,
        opportunity: OpportunityCandidate,
        result: ExecutionResult,
    ) -> None:
        """Save execution plan, legs, and PnL record to the database."""
        try:
            async with self._session_factory() as session:
                # Map state to model enum
                status_map = {
                    "PENDING": ExecutionPlanStatus.PENDING,
                    "SUBMITTING": ExecutionPlanStatus.SUBMITTING,
                    "PARTIAL_FILLED": ExecutionPlanStatus.PARTIAL_FILLED,
                    "FILLED": ExecutionPlanStatus.FILLED,
                    "COMPLETED": ExecutionPlanStatus.COMPLETED,
                    "FAILED": ExecutionPlanStatus.FAILED,
                    "HEDGING": ExecutionPlanStatus.HEDGING,
                    "ABORTED": ExecutionPlanStatus.ABORTED,
                }

                strategy_map = {
                    "CROSS_EXCHANGE": StrategyType.CROSS_EXCHANGE,
                    "TRIANGULAR": StrategyType.TRIANGULAR,
                }

                mode_enum = ExecutionMode.PAPER if result.mode == "PAPER" else ExecutionMode.LIVE

                plan = ExecutionPlan(
                    strategy_type=strategy_map.get(result.strategy_type, StrategyType.CROSS_EXCHANGE),
                    mode=mode_enum,
                    target_quantity=opportunity.executable_quantity,
                    target_value_usdt=opportunity.executable_value_usdt,
                    planned_profit_pct=result.planned_profit_pct,
                    status=status_map.get(result.state, ExecutionPlanStatus.FAILED),
                    started_at=datetime.fromtimestamp(result.started_at, tz=timezone.utc) if result.started_at else None,
                    completed_at=datetime.fromtimestamp(result.completed_at, tz=timezone.utc) if result.completed_at else None,
                    actual_profit_pct=result.actual_profit_pct,
                    actual_profit_usdt=result.actual_profit_usdt,
                    execution_time_ms=int(result.execution_time_ms),
                    error_message=result.error_message or None,
                    metadata_json={
                        "opportunity_id": opportunity.id,
                        "buy_exchange": opportunity.buy_exchange,
                        "sell_exchange": opportunity.sell_exchange,
                    },
                )
                session.add(plan)
                await session.flush()

                # Add legs
                leg_side_map = {"BUY": LegSide.BUY, "SELL": LegSide.SELL}
                leg_status_map = {
                    "PENDING": LegStatus.PENDING,
                    "SUBMITTED": LegStatus.SUBMITTED,
                    "PARTIAL_FILLED": LegStatus.PARTIAL_FILLED,
                    "FILLED": LegStatus.FILLED,
                    "CANCELED": LegStatus.CANCELED,
                    "FAILED": LegStatus.FAILED,
                }

                for leg_result in result.legs:
                    db_leg = ExecutionLeg(
                        execution_plan_id=plan.id,
                        leg_index=leg_result.leg_index,
                        exchange=leg_result.exchange,
                        symbol=leg_result.symbol,
                        side=leg_side_map.get(leg_result.side, LegSide.BUY),
                        planned_price=leg_result.planned_price,
                        planned_quantity=leg_result.planned_quantity,
                        actual_price=leg_result.actual_price or None,
                        actual_quantity=leg_result.actual_quantity or None,
                        fee=leg_result.fee or None,
                        fee_asset=leg_result.fee_asset or None,
                        slippage_pct=leg_result.slippage_pct or None,
                        exchange_order_id=leg_result.exchange_order_id or None,
                        status=leg_status_map.get(leg_result.status, LegStatus.FAILED),
                        submitted_at=(
                            datetime.fromtimestamp(leg_result.submitted_at, tz=timezone.utc)
                            if leg_result.submitted_at else None
                        ),
                        filled_at=(
                            datetime.fromtimestamp(leg_result.filled_at, tz=timezone.utc)
                            if leg_result.filled_at else None
                        ),
                        error_message=leg_result.error or None,
                    )
                    session.add(db_leg)

                # Create PnL record for completed executions
                if result.success:
                    pnl = PnlRecord(
                        execution_id=plan.id,
                        strategy_type=strategy_map.get(result.strategy_type, StrategyType.CROSS_EXCHANGE),
                        exchange_buy=opportunity.buy_exchange,
                        exchange_sell=opportunity.sell_exchange,
                        symbol=opportunity.symbols[0] if opportunity.symbols else opportunity.symbol,
                        gross_profit_usdt=result.gross_profit_usdt,
                        fees_usdt=result.total_fees_usdt,
                        net_profit_usdt=result.actual_profit_usdt,
                        slippage_usdt=result.total_slippage_usdt,
                        execution_time_ms=int(result.execution_time_ms),
                        mode=mode_enum,
                    )
                    session.add(pnl)

                await session.commit()
                logger.debug("Persisted execution {} to DB", result.execution_id)

        except Exception:
            logger.opt(exception=True).error("Failed to persist execution {}", result.execution_id)
