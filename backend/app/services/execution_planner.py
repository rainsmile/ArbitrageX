"""Builds ExecutionPlans from ArbitrageOpportunities with full risk context.

Converts scanner-produced :class:`OpportunityCandidate` objects into
structured :class:`ExecutionPlanData` instances ready for the coordinator
to execute.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.services.inventory import InventoryManager
from app.services.market_data import MarketDataService
from app.services.risk_engine import RiskContext, RiskDecision, RiskEngine
from app.services.scanner import OpportunityCandidate
from app.services.simulation import SimulationResult, SimulationService


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExecutionLegPlan:
    """Plan for a single execution leg."""
    leg_index: int
    exchange: str
    symbol: str
    side: str          # BUY / SELL
    order_type: str    # MARKET / LIMIT
    planned_price: float
    planned_quantity: float
    planned_notional: float
    fee_rate: float    # as a percentage, e.g. 0.1 means 0.1%

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg_index": self.leg_index,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "planned_price": self.planned_price,
            "planned_quantity": self.planned_quantity,
            "planned_notional": self.planned_notional,
            "fee_rate": self.fee_rate,
        }


@dataclass
class ExecutionPlanData:
    """Rich execution plan with risk context and simulation results."""
    plan_id: str
    opportunity_id: str
    strategy_type: str
    mode: str
    legs: list[ExecutionLegPlan]
    target_quantity: float
    target_notional_usdt: float
    planned_gross_profit: float
    planned_net_profit: float
    planned_net_profit_pct: float
    risk_check: RiskDecision
    simulation_result: SimulationResult | None
    pre_execution_snapshot: dict[str, Any]
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "opportunity_id": self.opportunity_id,
            "strategy_type": self.strategy_type,
            "mode": self.mode,
            "leg_count": len(self.legs),
            "legs": [leg.to_dict() for leg in self.legs],
            "target_quantity": self.target_quantity,
            "target_notional_usdt": self.target_notional_usdt,
            "planned_gross_profit": self.planned_gross_profit,
            "planned_net_profit": self.planned_net_profit,
            "planned_net_profit_pct": self.planned_net_profit_pct,
            "risk_approved": self.risk_check.approved,
            "risk_violations": [r.rule_name for r in self.risk_check.violations],
            "simulation_feasible": (
                self.simulation_result.feasible
                if self.simulation_result is not None
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum age (in seconds) for an opportunity to still be considered fresh.
_MAX_OPPORTUNITY_AGE_S = 10.0

# Default taker fee when exchange info is unavailable.
_DEFAULT_FEE_PCT = 0.10


# ---------------------------------------------------------------------------
# ExecutionPlanner
# ---------------------------------------------------------------------------

class ExecutionPlanner:
    """Converts scanner opportunities into structured execution plans."""

    def __init__(
        self,
        risk_engine: RiskEngine,
        inventory_manager: InventoryManager,
        market_data: MarketDataService,
        simulation_service: SimulationService,
    ) -> None:
        self._risk_engine = risk_engine
        self._inventory = inventory_manager
        self._market_data = market_data
        self._simulation = simulation_service

    # ------------------------------------------------------------------
    # Cross-exchange plan
    # ------------------------------------------------------------------

    async def build_cross_exchange_plan(
        self,
        opportunity: OpportunityCandidate,
        mode: str = "PAPER",
    ) -> ExecutionPlanData:
        """Build a full execution plan for a cross-exchange opportunity.

        Steps:
          1. Validate opportunity freshness
          2. Check balances on both exchanges
          3. Run risk engine pre-trade check
          4. Compute optimal execution quantity
          5. Build execution legs
          6. Run simulation for expected outcome
          7. Return complete plan with risk context
        """
        plan_id = uuid.uuid4().hex

        # 1. Validate freshness
        age = time.time() - opportunity.detected_at
        if age > _MAX_OPPORTUNITY_AGE_S:
            logger.warning(
                "Opportunity {} is {:.1f}s old (max {}s), building plan anyway",
                opportunity.id, age, _MAX_OPPORTUNITY_AGE_S,
            )

        # 2. Gather balance snapshot
        symbol = opportunity.symbols[0] if opportunity.symbols else opportunity.symbol
        parts = symbol.split("/") if "/" in symbol else []
        base_asset = parts[0] if len(parts) == 2 else ""
        quote_asset = parts[1] if len(parts) == 2 else ""

        buy_exchange = opportunity.buy_exchange
        sell_exchange = opportunity.sell_exchange

        buy_balance_snap = self._inventory.get_balance(buy_exchange, quote_asset)
        sell_balance_snap = self._inventory.get_balance(sell_exchange, base_asset)

        balances: dict[str, dict[str, float]] = {}
        if buy_balance_snap:
            balances.setdefault(buy_exchange, {})[quote_asset] = buy_balance_snap.free
        if sell_balance_snap:
            balances.setdefault(sell_exchange, {})[base_asset] = sell_balance_snap.free

        # Compute exchange exposure from inventory
        exchange_exposure: dict[str, float] = {}
        for alloc in self._inventory.get_exchange_allocation():
            exchange_exposure[alloc.exchange] = alloc.total_value_usdt

        # 3. Risk engine pre-trade check
        risk_context = RiskContext(
            balances=balances,
            exchange_exposure=exchange_exposure,
        )
        risk_decision = await self._risk_engine.evaluate(opportunity, context=risk_context)

        # 4. Compute optimal quantity (constrained by balance)
        target_quantity = opportunity.executable_quantity
        target_notional = opportunity.executable_value_usdt

        if buy_balance_snap and quote_asset and opportunity.buy_price > 0:
            max_buy_qty = buy_balance_snap.free / opportunity.buy_price
            target_quantity = min(target_quantity, max_buy_qty)

        if sell_balance_snap and base_asset:
            target_quantity = min(target_quantity, sell_balance_snap.free)

        if target_quantity > 0 and opportunity.buy_price > 0:
            target_notional = target_quantity * opportunity.buy_price

        # 5. Build execution legs
        buy_fee = opportunity.buy_fee_pct if opportunity.buy_fee_pct > 0 else _DEFAULT_FEE_PCT
        sell_fee = opportunity.sell_fee_pct if opportunity.sell_fee_pct > 0 else _DEFAULT_FEE_PCT

        legs = [
            ExecutionLegPlan(
                leg_index=0,
                exchange=buy_exchange,
                symbol=symbol,
                side="BUY",
                order_type="MARKET",
                planned_price=opportunity.buy_price,
                planned_quantity=target_quantity,
                planned_notional=target_quantity * opportunity.buy_price if opportunity.buy_price > 0 else 0.0,
                fee_rate=buy_fee,
            ),
            ExecutionLegPlan(
                leg_index=1,
                exchange=sell_exchange,
                symbol=symbol,
                side="SELL",
                order_type="MARKET",
                planned_price=opportunity.sell_price,
                planned_quantity=target_quantity,
                planned_notional=target_quantity * opportunity.sell_price if opportunity.sell_price > 0 else 0.0,
                fee_rate=sell_fee,
            ),
        ]

        # 6. Run simulation
        simulation_result: SimulationResult | None = None
        try:
            simulation_result = await self._simulation.simulate_cross_exchange(opportunity)
        except Exception:
            logger.opt(exception=True).warning(
                "Simulation failed for opportunity {}", opportunity.id,
            )

        # 7. Compute planned profits
        gross_profit = 0.0
        net_profit = 0.0
        if target_quantity > 0 and opportunity.buy_price > 0 and opportunity.sell_price > 0:
            buy_cost = target_quantity * opportunity.buy_price
            sell_revenue = target_quantity * opportunity.sell_price
            gross_profit = sell_revenue - buy_cost
            total_fees = (buy_cost * buy_fee / 100.0) + (sell_revenue * sell_fee / 100.0)
            net_profit = gross_profit - total_fees

        net_profit_pct = (
            (net_profit / target_notional * 100.0)
            if target_notional > 0
            else 0.0
        )

        # Pre-execution snapshot
        snapshot: dict[str, Any] = {
            "balances": balances,
            "exchange_exposure": exchange_exposure,
            "opportunity_age_s": age,
            "buy_ticker": self._ticker_snapshot(buy_exchange, symbol),
            "sell_ticker": self._ticker_snapshot(sell_exchange, symbol),
        }

        return ExecutionPlanData(
            plan_id=plan_id,
            opportunity_id=opportunity.id,
            strategy_type="CROSS_EXCHANGE",
            mode=mode,
            legs=legs,
            target_quantity=target_quantity,
            target_notional_usdt=target_notional,
            planned_gross_profit=gross_profit,
            planned_net_profit=net_profit,
            planned_net_profit_pct=net_profit_pct,
            risk_check=risk_decision,
            simulation_result=simulation_result,
            pre_execution_snapshot=snapshot,
            created_at=datetime.now(timezone.utc),
            metadata={
                "buy_exchange": buy_exchange,
                "sell_exchange": sell_exchange,
                "symbol": symbol,
                "spread_pct": opportunity.spread_pct,
            },
        )

    # ------------------------------------------------------------------
    # Triangular plan
    # ------------------------------------------------------------------

    async def build_triangular_plan(
        self,
        opportunity: OpportunityCandidate,
        mode: str = "PAPER",
    ) -> ExecutionPlanData:
        """Build a full execution plan for a triangular opportunity.

        Steps mirror :meth:`build_cross_exchange_plan` but handle 3 legs
        on a single exchange.
        """
        plan_id = uuid.uuid4().hex

        # Freshness check
        age = time.time() - opportunity.detected_at
        if age > _MAX_OPPORTUNITY_AGE_S:
            logger.warning(
                "Triangular opportunity {} is {:.1f}s old",
                opportunity.id, age,
            )

        symbols = opportunity.symbols
        if len(symbols) != 3:
            raise ValueError(
                f"Triangular opportunity requires 3 symbols, got {len(symbols)}"
            )

        exchange = opportunity.exchanges[0] if opportunity.exchanges else ""

        # Balance snapshot for the starting asset
        # Parse the first symbol to find the quote (starting) asset
        first_parts = symbols[0].split("/") if "/" in symbols[0] else []
        start_asset = first_parts[1] if len(first_parts) == 2 else "USDT"

        start_balance_snap = self._inventory.get_balance(exchange, start_asset)
        balances: dict[str, dict[str, float]] = {}
        if start_balance_snap:
            balances.setdefault(exchange, {})[start_asset] = start_balance_snap.free

        exchange_exposure: dict[str, float] = {}
        for alloc in self._inventory.get_exchange_allocation():
            exchange_exposure[alloc.exchange] = alloc.total_value_usdt

        # Risk check
        risk_context = RiskContext(
            balances=balances,
            exchange_exposure=exchange_exposure,
        )
        risk_decision = await self._risk_engine.evaluate(opportunity, context=risk_context)

        # Determine start amount
        start_amount = opportunity.executable_value_usdt
        if start_amount <= 0:
            start_amount = 100.0  # conservative default

        if start_balance_snap:
            start_amount = min(start_amount, start_balance_snap.free)

        # Build legs -- determine sides and prices from tickers
        sides = ["BUY", "BUY", "SELL"]  # standard triangular pattern
        fee_pct = opportunity.buy_fee_pct / 3.0 if opportunity.buy_fee_pct > 0 else _DEFAULT_FEE_PCT

        legs: list[ExecutionLegPlan] = []
        current_amount = start_amount

        for i, sym in enumerate(symbols):
            ticker = self._market_data.get_ticker(exchange, sym)
            side = sides[i] if i < len(sides) else "BUY"

            if ticker:
                price = ticker.ask if side == "BUY" else ticker.bid
            else:
                price = opportunity.buy_price if i == 0 else opportunity.sell_price

            if price <= 0:
                price = 1.0  # fallback to avoid division by zero

            if side == "BUY":
                quantity = current_amount / price
            else:
                quantity = current_amount

            notional = quantity * price

            legs.append(ExecutionLegPlan(
                leg_index=i,
                exchange=exchange,
                symbol=sym,
                side=side,
                order_type="MARKET",
                planned_price=price,
                planned_quantity=quantity,
                planned_notional=notional,
                fee_rate=fee_pct,
            ))

            # Update current_amount for next leg
            if side == "BUY":
                current_amount = quantity  # now holding base units
            else:
                current_amount = quantity * price  # converted back to quote

        # Simulation
        simulation_result: SimulationResult | None = None
        try:
            simulation_result = await self._simulation.simulate_triangular(opportunity)
        except Exception:
            logger.opt(exception=True).warning(
                "Triangular simulation failed for {}",
                opportunity.id,
            )

        # Profit estimation
        ending_amount = current_amount
        gross_profit = ending_amount - start_amount
        total_fee_pct = fee_pct * 3
        total_fees = start_amount * (total_fee_pct / 100.0)
        net_profit = gross_profit - total_fees
        net_profit_pct = (net_profit / start_amount * 100.0) if start_amount > 0 else 0.0

        snapshot: dict[str, Any] = {
            "balances": balances,
            "exchange_exposure": exchange_exposure,
            "opportunity_age_s": age,
            "start_asset": start_asset,
            "start_amount": start_amount,
        }
        for sym in symbols:
            snapshot[f"ticker:{exchange}:{sym}"] = self._ticker_snapshot(exchange, sym)

        return ExecutionPlanData(
            plan_id=plan_id,
            opportunity_id=opportunity.id,
            strategy_type="TRIANGULAR",
            mode=mode,
            legs=legs,
            target_quantity=start_amount,
            target_notional_usdt=start_amount,
            planned_gross_profit=gross_profit,
            planned_net_profit=net_profit,
            planned_net_profit_pct=net_profit_pct,
            risk_check=risk_decision,
            simulation_result=simulation_result,
            pre_execution_snapshot=snapshot,
            created_at=datetime.now(timezone.utc),
            metadata={
                "exchange": exchange,
                "path": ">".join(symbols),
                "start_asset": start_asset,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ticker_snapshot(self, exchange: str, symbol: str) -> dict[str, Any]:
        """Capture current ticker state for the pre-execution snapshot."""
        ticker = self._market_data.get_ticker(exchange, symbol)
        if ticker is None:
            return {"exchange": exchange, "symbol": symbol, "available": False}
        return {
            "exchange": exchange,
            "symbol": symbol,
            "available": True,
            "bid": ticker.bid,
            "ask": ticker.ask,
            "last": ticker.last_price,
            "data_age_s": self._market_data.get_data_age(exchange, symbol),
        }
