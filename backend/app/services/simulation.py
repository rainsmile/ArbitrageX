"""
SimulationService -- simulates order fills using orderbook depth, slippage
models, and fee schedules without touching real exchanges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.core.config import Settings, settings
from app.exchanges.base import OrderbookLevel, StandardOrderbook
from app.exchanges.factory import ExchangeFactory
from app.services.market_data import MarketDataService
from app.services.scanner import OpportunityCandidate


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SimulatedFill:
    """Result of simulating a single order."""
    exchange: str
    symbol: str
    side: str
    planned_price: float
    planned_quantity: float
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    fee_pct: float = 0.0
    fee_usdt: float = 0.0
    slippage_pct: float = 0.0
    slippage_usdt: float = 0.0
    notional_value: float = 0.0
    partial: bool = False
    levels_consumed: int = 0


@dataclass(slots=True)
class SimulatedLeg:
    """Simulated leg result aligned with execution engine's LegResult."""
    exchange: str
    symbol: str
    side: str
    planned_price: float
    planned_quantity: float
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    fee_pct: float = 0.0
    fee_usdt: float = 0.0
    slippage_pct: float = 0.0
    slippage_usdt: float = 0.0


@dataclass(slots=True)
class SimulationResult:
    """Full simulation outcome for an arbitrage opportunity."""
    strategy_type: str = "CROSS_EXCHANGE"
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_value_usdt: float = 0.0
    exit_value_usdt: float = 0.0
    gross_profit_usdt: float = 0.0
    total_fees_usdt: float = 0.0
    total_slippage_usdt: float = 0.0
    net_profit_usdt: float = 0.0
    net_profit_pct: float = 0.0
    legs: list[SimulatedLeg] = field(default_factory=list)
    feasible: bool = True
    reason: str = ""


# ---------------------------------------------------------------------------
# Slippage models
# ---------------------------------------------------------------------------

class FixedSlippageModel:
    """Apply a fixed percentage slippage regardless of size."""

    def __init__(self, slippage_pct: float = 0.05) -> None:
        self.slippage_pct = slippage_pct

    def apply(self, price: float, side: str) -> float:
        if side == "BUY":
            return price * (1 + self.slippage_pct / 100.0)
        return price * (1 - self.slippage_pct / 100.0)


class DepthBasedSlippageModel:
    """Calculate slippage by walking the orderbook."""

    def walk_book(
        self,
        levels: list[OrderbookLevel],
        quantity: float,
    ) -> tuple[float, float, int]:
        """Walk orderbook levels to fill *quantity*.

        Returns (avg_fill_price, filled_quantity, levels_consumed).
        """
        filled_qty = 0.0
        total_cost = 0.0
        consumed = 0

        for level in levels:
            if filled_qty >= quantity:
                break
            if level.price <= 0 or level.quantity <= 0:
                continue

            remaining = quantity - filled_qty
            fill_at_level = min(level.quantity, remaining)
            total_cost += fill_at_level * level.price
            filled_qty += fill_at_level
            consumed += 1

        avg_price = total_cost / filled_qty if filled_qty > 0 else 0.0
        return avg_price, filled_qty, consumed


# ---------------------------------------------------------------------------
# Fee models
# ---------------------------------------------------------------------------

# Default taker fees by exchange (percentage)
_DEFAULT_FEES: dict[str, dict[str, float]] = {
    "binance": {"maker": 0.10, "taker": 0.10},
    "okx": {"maker": 0.08, "taker": 0.10},
    "bybit": {"maker": 0.10, "taker": 0.10},
    "kraken": {"maker": 0.16, "taker": 0.26},
    "kucoin": {"maker": 0.10, "taker": 0.10},
    "gate": {"maker": 0.15, "taker": 0.15},
    "htx": {"maker": 0.20, "taker": 0.20},
    "bitget": {"maker": 0.10, "taker": 0.10},
    "mexc": {"maker": 0.00, "taker": 0.10},
    "mock_binance": {"maker": 0.10, "taker": 0.10},
    "mock_okx": {"maker": 0.08, "taker": 0.10},
    "mock_bybit": {"maker": 0.10, "taker": 0.10},
}


def _get_taker_fee_pct(exchange: str) -> float:
    """Get taker fee as a percentage (e.g. 0.1 means 0.1%)."""
    fees = _DEFAULT_FEES.get(exchange, {})
    return fees.get("taker", 0.10)


# ---------------------------------------------------------------------------
# SimulationService
# ---------------------------------------------------------------------------

class SimulationService:
    """Simulates order execution using orderbook depth and fee models.

    Used for paper trading and pre-execution analysis.
    """

    def __init__(
        self,
        market_data: MarketDataService,
        exchange_factory: ExchangeFactory,
        config: Settings | None = None,
    ) -> None:
        self._market_data = market_data
        self._exchange_factory = exchange_factory
        self._cfg = config or settings
        self._depth_model = DepthBasedSlippageModel()
        self._fixed_model = FixedSlippageModel(slippage_pct=0.05)
        self._slippage_mode: str = "depth"  # "depth" or "fixed"

    @property
    def slippage_mode(self) -> str:
        return self._slippage_mode

    @slippage_mode.setter
    def slippage_mode(self, mode: str) -> None:
        if mode not in ("depth", "fixed"):
            raise ValueError(f"Unknown slippage mode: {mode}")
        self._slippage_mode = mode

    # ------------------------------------------------------------------
    # Single order simulation
    # ------------------------------------------------------------------

    def simulate_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        orderbook: StandardOrderbook | None = None,
    ) -> SimulatedFill:
        """Simulate a single market order against the orderbook.

        If no orderbook is provided, falls back to the market data cache.
        If still no data, uses the fixed slippage model.
        """
        if orderbook is None:
            orderbook = self._market_data.get_orderbook(exchange, symbol)

        ticker = self._market_data.get_ticker(exchange, symbol)
        reference_price = 0.0
        if ticker:
            reference_price = ticker.ask if side == "BUY" else ticker.bid

        fill = SimulatedFill(
            exchange=exchange,
            symbol=symbol,
            side=side,
            planned_price=reference_price,
            planned_quantity=quantity,
        )

        fee_pct = _get_taker_fee_pct(exchange)
        fill.fee_pct = fee_pct

        if orderbook and self._slippage_mode == "depth":
            # Walk the orderbook
            levels = orderbook.asks if side == "BUY" else orderbook.bids
            avg_price, filled_qty, consumed = self._depth_model.walk_book(levels, quantity)

            if filled_qty <= 0:
                # Orderbook too thin -- mark as partial/infeasible
                fill.fill_price = reference_price
                fill.fill_quantity = 0.0
                fill.partial = True
                fill.levels_consumed = 0
                return fill

            fill.fill_price = avg_price
            fill.fill_quantity = filled_qty
            fill.levels_consumed = consumed
            fill.partial = filled_qty < quantity

            # Slippage relative to top-of-book
            top_price = levels[0].price if levels else reference_price
            if top_price > 0:
                if side == "BUY":
                    fill.slippage_pct = (avg_price - top_price) / top_price * 100.0
                else:
                    fill.slippage_pct = (top_price - avg_price) / top_price * 100.0
        else:
            # Fixed slippage model
            adjusted_price = self._fixed_model.apply(reference_price, side)
            fill.fill_price = adjusted_price
            fill.fill_quantity = quantity
            fill.partial = False
            if reference_price > 0:
                fill.slippage_pct = abs(adjusted_price - reference_price) / reference_price * 100.0

        # Calculate fees and notional
        notional = fill.fill_price * fill.fill_quantity
        fill.notional_value = notional
        fill.fee_usdt = notional * (fee_pct / 100.0)
        fill.slippage_usdt = abs(fill.fill_price - fill.planned_price) * fill.fill_quantity

        return fill

    # ------------------------------------------------------------------
    # Cross-exchange simulation
    # ------------------------------------------------------------------

    async def simulate_cross_exchange(
        self,
        opportunity: OpportunityCandidate,
    ) -> SimulationResult:
        """Simulate a full cross-exchange arbitrage execution."""
        result = SimulationResult(strategy_type="CROSS_EXCHANGE")

        symbol = opportunity.symbols[0] if opportunity.symbols else opportunity.symbol
        quantity = opportunity.executable_quantity

        if quantity <= 0:
            result.feasible = False
            result.reason = "Zero executable quantity"
            return result

        # Simulate buy leg
        buy_ob = self._market_data.get_orderbook(opportunity.buy_exchange, symbol)
        buy_fill = self.simulate_order(
            exchange=opportunity.buy_exchange,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            orderbook=buy_ob,
        )

        # Simulate sell leg (use actual filled quantity from buy side)
        sell_qty = buy_fill.fill_quantity
        if sell_qty <= 0:
            result.feasible = False
            result.reason = "Buy side fill quantity is zero"
            return result

        sell_ob = self._market_data.get_orderbook(opportunity.sell_exchange, symbol)
        sell_fill = self.simulate_order(
            exchange=opportunity.sell_exchange,
            symbol=symbol,
            side="SELL",
            quantity=sell_qty,
            orderbook=sell_ob,
        )

        if sell_fill.fill_quantity <= 0:
            result.feasible = False
            result.reason = "Sell side fill quantity is zero"
            return result

        # Use the minimum of both filled quantities
        effective_qty = min(buy_fill.fill_quantity, sell_fill.fill_quantity)

        entry_value = effective_qty * buy_fill.fill_price
        exit_value = effective_qty * sell_fill.fill_price
        gross_profit = exit_value - entry_value
        total_fees = buy_fill.fee_usdt + sell_fill.fee_usdt
        total_slippage = buy_fill.slippage_usdt + sell_fill.slippage_usdt
        net_profit = gross_profit - total_fees

        result.entry_price = buy_fill.fill_price
        result.exit_price = sell_fill.fill_price
        result.entry_value_usdt = entry_value
        result.exit_value_usdt = exit_value
        result.gross_profit_usdt = gross_profit
        result.total_fees_usdt = total_fees
        result.total_slippage_usdt = total_slippage
        result.net_profit_usdt = net_profit
        result.net_profit_pct = (net_profit / entry_value * 100.0) if entry_value > 0 else 0.0
        result.feasible = net_profit > 0

        result.legs = [
            SimulatedLeg(
                exchange=buy_fill.exchange,
                symbol=buy_fill.symbol,
                side="BUY",
                planned_price=buy_fill.planned_price,
                planned_quantity=buy_fill.planned_quantity,
                fill_price=buy_fill.fill_price,
                fill_quantity=buy_fill.fill_quantity,
                fee_pct=buy_fill.fee_pct,
                fee_usdt=buy_fill.fee_usdt,
                slippage_pct=buy_fill.slippage_pct,
                slippage_usdt=buy_fill.slippage_usdt,
            ),
            SimulatedLeg(
                exchange=sell_fill.exchange,
                symbol=sell_fill.symbol,
                side="SELL",
                planned_price=sell_fill.planned_price,
                planned_quantity=sell_fill.planned_quantity,
                fill_price=sell_fill.fill_price,
                fill_quantity=sell_fill.fill_quantity,
                fee_pct=sell_fill.fee_pct,
                fee_usdt=sell_fill.fee_usdt,
                slippage_pct=sell_fill.slippage_pct,
                slippage_usdt=sell_fill.slippage_usdt,
            ),
        ]

        if not result.reason:
            result.reason = "Profitable" if result.feasible else "Net profit is negative after fees"

        logger.debug(
            "Simulated cross-exchange {}: entry={:.2f} exit={:.2f} net={:.4f} USDT",
            symbol, entry_value, exit_value, net_profit,
        )

        return result

    # ------------------------------------------------------------------
    # Triangular simulation
    # ------------------------------------------------------------------

    async def simulate_triangular(
        self,
        opportunity: OpportunityCandidate,
    ) -> SimulationResult:
        """Simulate a full triangular arbitrage execution."""
        result = SimulationResult(strategy_type="TRIANGULAR")

        symbols = opportunity.symbols
        if len(symbols) != 3:
            result.feasible = False
            result.reason = f"Need 3 symbols for triangular, got {len(symbols)}"
            return result

        exchange = opportunity.exchanges[0] if opportunity.exchanges else ""
        if not exchange:
            result.feasible = False
            result.reason = "No exchange specified"
            return result

        # Parse the path from opportunity.symbol (e.g. "BTC/USDT>ETH/BTC>ETH/USDT")
        sides = ["BUY", "BUY", "SELL"]  # Default pattern

        # Start with a notional 100 USDT (or use executable_value)
        starting_value = opportunity.executable_value_usdt if opportunity.executable_value_usdt > 0 else 100.0

        legs: list[SimulatedLeg] = []
        current_amount = starting_value
        total_fees = 0.0
        total_slippage = 0.0

        for i, (sym, side) in enumerate(zip(symbols, sides)):
            ticker = self._market_data.get_ticker(exchange, sym)
            if not ticker:
                result.feasible = False
                result.reason = f"No ticker for {exchange}:{sym}"
                return result

            # Determine quantity based on current amount
            if side == "BUY":
                # Spending current_amount to buy base asset
                price = ticker.ask
                if price <= 0:
                    result.feasible = False
                    result.reason = f"Zero ask price for {sym}"
                    return result
                quantity = current_amount / price
            else:
                # Selling current_amount units of base asset
                price = ticker.bid
                if price <= 0:
                    result.feasible = False
                    result.reason = f"Zero bid price for {sym}"
                    return result
                quantity = current_amount

            ob = self._market_data.get_orderbook(exchange, sym)
            fill = self.simulate_order(
                exchange=exchange,
                symbol=sym,
                side=side,
                quantity=quantity,
                orderbook=ob,
            )

            if fill.fill_quantity <= 0:
                result.feasible = False
                result.reason = f"Zero fill on leg {i} ({sym})"
                return result

            leg = SimulatedLeg(
                exchange=exchange,
                symbol=sym,
                side=side,
                planned_price=price,
                planned_quantity=quantity,
                fill_price=fill.fill_price,
                fill_quantity=fill.fill_quantity,
                fee_pct=fill.fee_pct,
                fee_usdt=fill.fee_usdt,
                slippage_pct=fill.slippage_pct,
                slippage_usdt=fill.slippage_usdt,
            )
            legs.append(leg)
            total_fees += fill.fee_usdt
            total_slippage += fill.slippage_usdt

            # Update current_amount for next leg
            if side == "BUY":
                current_amount = fill.fill_quantity  # We now hold this many base units
            else:
                current_amount = fill.fill_quantity * fill.fill_price  # Convert to quote

        # Final PnL
        ending_value = current_amount
        gross_profit = ending_value - starting_value
        net_profit = gross_profit - total_fees

        result.entry_value_usdt = starting_value
        result.exit_value_usdt = ending_value
        result.gross_profit_usdt = gross_profit
        result.total_fees_usdt = total_fees
        result.total_slippage_usdt = total_slippage
        result.net_profit_usdt = net_profit
        result.net_profit_pct = (net_profit / starting_value * 100.0) if starting_value > 0 else 0.0
        result.legs = legs
        result.feasible = net_profit > 0
        result.reason = "Profitable" if result.feasible else "Net profit is negative"

        logger.debug(
            "Simulated triangular on {}: start={:.2f} end={:.2f} net={:.4f} USDT",
            exchange, starting_value, ending_value, net_profit,
        )

        return result
