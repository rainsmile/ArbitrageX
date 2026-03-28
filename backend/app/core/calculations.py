"""
Core trading calculation functions.

All functions are pure — no side effects, no I/O, no service dependencies.
This makes them trivially testable and reusable across scanner, simulation,
and execution modules.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Optional


# ─── Result Data Classes ────────────────────────────────────────────

@dataclass(slots=True)
class DepthWalkResult:
    """Result of walking an orderbook to fill a target quantity."""
    filled_quantity: float
    average_price: float
    total_cost: float  # quantity * avg_price
    levels_consumed: int
    is_fully_filled: bool
    shortfall_quantity: float  # how much couldn't be filled
    worst_price: float  # price of last level consumed
    price_impact_pct: float  # (avg_price - best_price) / best_price * 100


@dataclass(slots=True)
class FeeEstimate:
    """Fee breakdown for a single order."""
    fee_rate: float  # e.g. 0.001 for 0.1%
    fee_amount: float  # in quote currency
    fee_asset: str  # e.g. "USDT"


@dataclass(slots=True)
class SlippageEstimate:
    """Slippage estimation result."""
    natural_slippage_pct: float  # from orderbook depth walking
    buffer_slippage_pct: float  # safety buffer
    total_slippage_pct: float
    slippage_cost: float  # in quote currency


@dataclass(slots=True)
class ExecutableQuantityResult:
    """Result of computing max executable quantity for an arb opportunity."""
    quantity: float
    buy_avg_price: float
    sell_avg_price: float
    buy_depth_sufficient: bool
    sell_depth_sufficient: bool
    limited_by: str  # "buy_depth" | "sell_depth" | "balance" | "max_notional" | "min_quantity" | "none"
    buy_cost: float
    sell_proceeds: float


@dataclass(slots=True)
class NetProfitResult:
    """Complete profit/loss breakdown for an arbitrage opportunity."""
    gross_profit: float  # sell_proceeds - buy_cost (before fees/slippage)
    gross_profit_pct: float
    buy_fee: float
    sell_fee: float
    total_fees: float
    buy_slippage_cost: float
    sell_slippage_cost: float
    total_slippage_cost: float
    net_profit: float  # gross - fees - slippage
    net_profit_pct: float  # net_profit / buy_cost * 100
    is_profitable: bool
    breakeven_spread_pct: float  # minimum spread needed to break even


@dataclass(slots=True)
class TriangularProfitResult:
    """Profit calculation for a triangular arbitrage path."""
    start_amount: float
    end_amount: float
    leg1_rate: float
    leg2_rate: float
    leg3_rate: float
    leg1_fee: float
    leg2_fee: float
    leg3_fee: float
    total_fees: float
    gross_profit: float
    net_profit: float
    net_profit_pct: float
    is_profitable: bool
    implied_rate: float  # product of all legs
    debug_steps: list[dict]  # step-by-step calculation trace


@dataclass(slots=True)
class OpportunityDebugDetails:
    """Complete debug trace for opportunity detection - for replay/audit."""
    buy_orderbook_top5: list[tuple[float, float]]  # (price, qty) top 5 asks
    sell_orderbook_top5: list[tuple[float, float]]  # (price, qty) top 5 bids
    buy_depth_walk: DepthWalkResult
    sell_depth_walk: DepthWalkResult
    fee_buy: FeeEstimate
    fee_sell: FeeEstimate
    slippage_buy: SlippageEstimate
    slippage_sell: SlippageEstimate
    executable_qty: ExecutableQuantityResult
    profit: NetProfitResult
    calculation_timestamp_ms: int


# ─── Pure Functions ─────────────────────────────────────────────────

def walk_orderbook_depth(
    levels: list[tuple[float, float]],
    target_quantity: float,
    side: str,
) -> DepthWalkResult:
    """Walk an orderbook to fill *target_quantity* and compute fill statistics.

    Parameters
    ----------
    levels:
        List of ``(price, quantity)`` tuples.

        * For ``side="buy"`` these are **asks**, sorted price-ascending
          (cheapest first).
        * For ``side="sell"`` these are **bids**, sorted price-descending
          (most expensive first).
    target_quantity:
        Desired fill quantity in base asset.
    side:
        ``"buy"`` or ``"sell"``.

    Returns
    -------
    DepthWalkResult

    Examples
    --------
    >>> asks = [(100.0, 1.0), (101.0, 2.0), (102.0, 3.0)]
    >>> r = walk_orderbook_depth(asks, 2.5, "buy")
    >>> r.filled_quantity
    2.5
    >>> r.is_fully_filled
    True
    >>> r.levels_consumed
    2
    >>> round(r.average_price, 4)
    100.6
    """
    if target_quantity <= 0 or not levels:
        return DepthWalkResult(
            filled_quantity=0.0,
            average_price=0.0,
            total_cost=0.0,
            levels_consumed=0,
            is_fully_filled=(target_quantity <= 0),
            shortfall_quantity=max(target_quantity, 0.0),
            worst_price=0.0,
            price_impact_pct=0.0,
        )

    filled = 0.0
    total_cost = 0.0
    levels_consumed = 0
    best_price = levels[0][0]
    worst_price = best_price

    for price, qty in levels:
        if qty <= 0:
            continue
        remaining = target_quantity - filled
        if remaining <= 0:
            break
        take = min(qty, remaining)
        filled += take
        total_cost += take * price
        worst_price = price
        levels_consumed += 1
        if filled >= target_quantity:
            break

    avg_price = total_cost / filled if filled > 0 else 0.0
    is_fully_filled = filled >= target_quantity

    # Price impact: for buys, avg > best means we paid more; for sells,
    # avg < best means we received less.  Both cases captured by the
    # absolute relative difference.
    if best_price > 0:
        price_impact_pct = abs(avg_price - best_price) / best_price * 100.0
    else:
        price_impact_pct = 0.0

    return DepthWalkResult(
        filled_quantity=filled,
        average_price=avg_price,
        total_cost=total_cost,
        levels_consumed=levels_consumed,
        is_fully_filled=is_fully_filled,
        shortfall_quantity=max(target_quantity - filled, 0.0),
        worst_price=worst_price,
        price_impact_pct=price_impact_pct,
    )


def estimate_fee(
    quantity: float,
    price: float,
    fee_rate: float,
    quote_asset: str = "USDT",
) -> FeeEstimate:
    """Compute the trading fee for a single order in quote currency.

    Parameters
    ----------
    quantity:
        Order quantity in base asset.
    price:
        Execution price per unit of base asset.
    fee_rate:
        Fee as a decimal fraction, e.g. ``0.001`` for 0.1 %.
    quote_asset:
        Quote asset symbol for the ``fee_asset`` field.

    Returns
    -------
    FeeEstimate

    Examples
    --------
    >>> f = estimate_fee(1.0, 50000.0, 0.001)
    >>> f.fee_amount
    50.0
    >>> f.fee_asset
    'USDT'
    """
    notional = quantity * price
    fee_amount = notional * fee_rate
    return FeeEstimate(
        fee_rate=fee_rate,
        fee_amount=fee_amount,
        fee_asset=quote_asset,
    )


def estimate_slippage(
    best_price: float,
    avg_fill_price: float,
    side: str,
    buffer_bps: float = 5.0,
) -> SlippageEstimate:
    """Estimate slippage from depth-walk results plus a safety buffer.

    Parameters
    ----------
    best_price:
        Top-of-book price (best ask for buys, best bid for sells).
    avg_fill_price:
        Volume-weighted average fill price from ``walk_orderbook_depth``.
    side:
        ``"buy"`` or ``"sell"``.
    buffer_bps:
        Additional safety buffer in basis points (1 bp = 0.01 %).

    Returns
    -------
    SlippageEstimate
        ``slippage_cost`` is a per-unit cost; multiply by quantity externally
        to get total cost.

    Examples
    --------
    >>> s = estimate_slippage(100.0, 100.5, "buy", buffer_bps=5.0)
    >>> round(s.natural_slippage_pct, 2)
    0.5
    >>> round(s.buffer_slippage_pct, 2)
    0.05
    >>> round(s.total_slippage_pct, 2)
    0.55
    """
    if best_price <= 0:
        return SlippageEstimate(
            natural_slippage_pct=0.0,
            buffer_slippage_pct=0.0,
            total_slippage_pct=0.0,
            slippage_cost=0.0,
        )

    natural_pct = abs(avg_fill_price - best_price) / best_price * 100.0
    buffer_pct = buffer_bps / 100.0  # bps -> percent
    total_pct = natural_pct + buffer_pct

    # Cost per unit of base asset in quote terms
    slippage_cost = total_pct / 100.0 * best_price

    return SlippageEstimate(
        natural_slippage_pct=natural_pct,
        buffer_slippage_pct=buffer_pct,
        total_slippage_pct=total_pct,
        slippage_cost=slippage_cost,
    )


def truncate_to_step_size(quantity: float, step_size: float) -> float:
    """Truncate *quantity* down to the nearest multiple of *step_size*.

    Uses ``Decimal`` arithmetic to avoid floating-point rounding artefacts.

    Parameters
    ----------
    quantity:
        Raw quantity to truncate.
    step_size:
        Minimum increment (e.g. 0.001 for 3-decimal precision).

    Returns
    -------
    float
        Truncated quantity, always ``<= quantity``.

    Examples
    --------
    >>> truncate_to_step_size(1.23456, 0.001)
    1.234
    >>> truncate_to_step_size(0.999, 0.01)
    0.99
    >>> truncate_to_step_size(5.0, 0.0)
    5.0
    """
    if step_size <= 0:
        return quantity
    d_qty = Decimal(str(quantity))
    d_step = Decimal(str(step_size))
    truncated = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
    return float(truncated)


def compute_executable_quantity(
    buy_asks: list[tuple[float, float]],
    sell_bids: list[tuple[float, float]],
    buy_balance_quote: float,
    sell_balance_base: float,
    max_notional_usdt: float = 10000.0,
    min_quantity: float = 0.0,
    step_size: float = 0.0,
) -> ExecutableQuantityResult:
    """Compute the maximum executable quantity for a cross-exchange arb.

    The function intersects four constraints:

    1. **Buy depth** -- how much the buy-side asks can fill.
    2. **Sell depth** -- how much the sell-side bids can fill.
    3. **Buy balance** -- how much we can afford at the buy exchange.
    4. **Sell balance** -- how much base asset we hold at the sell exchange.
    5. **Max notional** -- position-size cap in quote currency.
    6. **Min quantity / step size** -- exchange lot filters.

    Parameters
    ----------
    buy_asks:
        ``(price, qty)`` tuples, price-ascending.
    sell_bids:
        ``(price, qty)`` tuples, price-descending.
    buy_balance_quote:
        Available quote (e.g. USDT) balance on the buy exchange.
    sell_balance_base:
        Available base (e.g. BTC) balance on the sell exchange.
    max_notional_usdt:
        Maximum notional value of the trade in USDT.
    min_quantity:
        Minimum order quantity imposed by exchange filters.
    step_size:
        Lot-size step for quantity rounding.

    Returns
    -------
    ExecutableQuantityResult

    Examples
    --------
    >>> asks = [(100.0, 5.0), (101.0, 5.0)]
    >>> bids = [(102.0, 5.0), (101.5, 5.0)]
    >>> r = compute_executable_quantity(asks, bids, 500.0, 10.0, 10000.0)
    >>> r.quantity  # limited by buy balance: 500 / 100 ~ 5 units at first level
    5.0
    >>> r.limited_by
    'balance'
    """
    # --- total depth available on each side ---
    total_ask_qty = sum(q for _, q in buy_asks if q > 0)
    total_bid_qty = sum(q for _, q in sell_bids if q > 0)

    # --- how much can we buy with our quote balance? ---
    # Walk asks accumulating cost until balance exhausted
    buy_max_qty = 0.0
    buy_cost_acc = 0.0
    for price, qty in buy_asks:
        if qty <= 0 or price <= 0:
            continue
        affordable_qty = (buy_balance_quote - buy_cost_acc) / price
        if affordable_qty <= 0:
            break
        take = min(qty, affordable_qty)
        buy_max_qty += take
        buy_cost_acc += take * price

    # --- constrain by sell-side base balance ---
    sell_max_qty = min(total_bid_qty, sell_balance_base)

    # --- candidate quantity is the minimum across all constraints ---
    qty = min(buy_max_qty, sell_max_qty)

    # Track the binding constraint
    limited_by = "none"
    if qty <= 0:
        if buy_max_qty <= 0 and sell_max_qty <= 0:
            limited_by = "buy_depth"  # both empty, pick buy
        elif buy_max_qty <= sell_max_qty:
            limited_by = "balance" if buy_max_qty < total_ask_qty else "buy_depth"
        else:
            limited_by = "sell_depth" if sell_max_qty <= total_bid_qty and total_bid_qty <= sell_balance_base else "balance"
    elif buy_max_qty <= sell_max_qty:
        # buy side was the bottleneck
        if buy_max_qty < total_ask_qty:
            limited_by = "balance"
        else:
            limited_by = "buy_depth"
    else:
        # sell side was the bottleneck
        if sell_max_qty < total_bid_qty:
            # limited by base balance on sell exchange
            limited_by = "balance"
        else:
            limited_by = "sell_depth"

    # --- apply max_notional cap ---
    if qty > 0 and buy_asks:
        # Estimate notional at best ask to check cap
        best_ask = buy_asks[0][0]
        if best_ask > 0:
            max_qty_by_notional = max_notional_usdt / best_ask
            if qty > max_qty_by_notional:
                qty = max_qty_by_notional
                limited_by = "max_notional"

    # --- apply step_size truncation ---
    if step_size > 0:
        qty = truncate_to_step_size(qty, step_size)

    # --- apply min_quantity filter ---
    if 0 < qty < min_quantity:
        return ExecutableQuantityResult(
            quantity=0.0,
            buy_avg_price=0.0,
            sell_avg_price=0.0,
            buy_depth_sufficient=False,
            sell_depth_sufficient=False,
            limited_by="min_quantity",
            buy_cost=0.0,
            sell_proceeds=0.0,
        )

    # --- final depth walks at the resolved quantity ---
    buy_walk = walk_orderbook_depth(buy_asks, qty, "buy")
    sell_walk = walk_orderbook_depth(sell_bids, qty, "sell")

    return ExecutableQuantityResult(
        quantity=qty,
        buy_avg_price=buy_walk.average_price,
        sell_avg_price=sell_walk.average_price,
        buy_depth_sufficient=buy_walk.is_fully_filled,
        sell_depth_sufficient=sell_walk.is_fully_filled,
        limited_by=limited_by,
        buy_cost=buy_walk.total_cost,
        sell_proceeds=sell_walk.total_cost,
    )


def compute_net_profit(
    buy_quantity: float,
    buy_avg_price: float,
    sell_quantity: float,
    sell_avg_price: float,
    buy_fee_rate: float,
    sell_fee_rate: float,
    slippage_buffer_bps: float = 5.0,
    buy_best_price: float = 0.0,
    sell_best_price: float = 0.0,
) -> NetProfitResult:
    """Compute the full profit/loss breakdown for an arbitrage trade.

    Parameters
    ----------
    buy_quantity:
        Quantity being purchased.
    buy_avg_price:
        Volume-weighted average buy price.
    sell_quantity:
        Quantity being sold (usually equal to ``buy_quantity``).
    sell_avg_price:
        Volume-weighted average sell price.
    buy_fee_rate:
        Taker fee rate on the buy exchange (decimal, e.g. 0.001).
    sell_fee_rate:
        Taker fee rate on the sell exchange.
    slippage_buffer_bps:
        Safety buffer in basis points applied to both legs.
    buy_best_price:
        Best ask on the buy exchange (for slippage estimation).  Falls back
        to ``buy_avg_price`` when ``0``.
    sell_best_price:
        Best bid on the sell exchange.  Falls back to ``sell_avg_price``
        when ``0``.

    Returns
    -------
    NetProfitResult

    Examples
    --------
    >>> r = compute_net_profit(
    ...     buy_quantity=1.0, buy_avg_price=100.0,
    ...     sell_quantity=1.0, sell_avg_price=102.0,
    ...     buy_fee_rate=0.001, sell_fee_rate=0.001,
    ...     slippage_buffer_bps=0.0,
    ...     buy_best_price=100.0, sell_best_price=102.0,
    ... )
    >>> r.gross_profit
    2.0
    >>> r.is_profitable
    True
    """
    if buy_best_price <= 0:
        buy_best_price = buy_avg_price
    if sell_best_price <= 0:
        sell_best_price = sell_avg_price

    buy_cost = buy_quantity * buy_avg_price
    sell_proceeds = sell_quantity * sell_avg_price

    gross_profit = sell_proceeds - buy_cost
    gross_profit_pct = (gross_profit / buy_cost * 100.0) if buy_cost > 0 else 0.0

    # Fees
    buy_fee = buy_cost * buy_fee_rate
    sell_fee = sell_proceeds * sell_fee_rate
    total_fees = buy_fee + sell_fee

    # Slippage
    buy_slip = estimate_slippage(buy_best_price, buy_avg_price, "buy", slippage_buffer_bps)
    sell_slip = estimate_slippage(sell_best_price, sell_avg_price, "sell", slippage_buffer_bps)
    buy_slippage_cost = buy_slip.slippage_cost * buy_quantity
    sell_slippage_cost = sell_slip.slippage_cost * sell_quantity
    total_slippage_cost = buy_slippage_cost + sell_slippage_cost

    net_profit = gross_profit - total_fees - total_slippage_cost
    net_profit_pct = (net_profit / buy_cost * 100.0) if buy_cost > 0 else 0.0

    # Breakeven: the minimum spread % that just covers fees + slippage buffer
    # fees on both sides as pct of buy cost + slippage buffers
    fee_pct = (buy_fee_rate + sell_fee_rate) * 100.0
    buffer_pct = slippage_buffer_bps / 100.0 * 2  # both legs
    breakeven_spread_pct = fee_pct + buffer_pct

    return NetProfitResult(
        gross_profit=gross_profit,
        gross_profit_pct=gross_profit_pct,
        buy_fee=buy_fee,
        sell_fee=sell_fee,
        total_fees=total_fees,
        buy_slippage_cost=buy_slippage_cost,
        sell_slippage_cost=sell_slippage_cost,
        total_slippage_cost=total_slippage_cost,
        net_profit=net_profit,
        net_profit_pct=net_profit_pct,
        is_profitable=net_profit > 0,
        breakeven_spread_pct=breakeven_spread_pct,
    )


def compute_triangular_profit(
    start_amount: float,
    legs: list[dict],
) -> TriangularProfitResult:
    """Simulate a triangular arbitrage path and compute profit.

    Each leg is a dict with keys ``"price"``, ``"side"``, and ``"fee_rate"``.

    * ``side="buy"``  -- spend quote to acquire base:
      ``amount_out = amount_in / price * (1 - fee_rate)``
    * ``side="sell"`` -- sell base to receive quote:
      ``amount_out = amount_in * price * (1 - fee_rate)``

    Parameters
    ----------
    start_amount:
        Initial capital in the starting asset.
    legs:
        Ordered list of leg descriptors.  Exactly 3 legs for a triangle.

    Returns
    -------
    TriangularProfitResult

    Examples
    --------
    >>> legs = [
    ...     {"price": 50000.0, "side": "buy",  "fee_rate": 0.001},
    ...     {"price": 3400.0,  "side": "sell", "fee_rate": 0.001},
    ...     {"price": 0.068,   "side": "sell", "fee_rate": 0.001},
    ... ]
    >>> r = compute_triangular_profit(10000.0, legs)
    >>> r.start_amount
    10000.0
    """
    if not legs:
        return TriangularProfitResult(
            start_amount=start_amount,
            end_amount=start_amount,
            leg1_rate=0.0,
            leg2_rate=0.0,
            leg3_rate=0.0,
            leg1_fee=0.0,
            leg2_fee=0.0,
            leg3_fee=0.0,
            total_fees=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            net_profit_pct=0.0,
            is_profitable=False,
            implied_rate=0.0,
            debug_steps=[],
        )

    amount = start_amount
    debug_steps: list[dict] = []
    fees: list[float] = []
    rates: list[float] = []
    implied_rate = 1.0

    for i, leg in enumerate(legs):
        price = leg["price"]
        side = leg["side"]
        fee_rate = leg["fee_rate"]
        amount_in = amount

        if side == "buy":
            # Buying base with quote: qty_base = amount_quote / price
            raw_out = amount_in / price if price > 0 else 0.0
            fee_amount = raw_out * fee_rate
            amount_out = raw_out - fee_amount
            effective_rate = 1.0 / price if price > 0 else 0.0
            implied_rate *= effective_rate * (1 - fee_rate)
        else:  # sell
            # Selling base for quote: amount_quote = amount_base * price
            raw_out = amount_in * price
            fee_amount = raw_out * fee_rate
            amount_out = raw_out - fee_amount
            effective_rate = price
            implied_rate *= effective_rate * (1 - fee_rate)

        # Fee in the *output* asset units; convert back to input-equivalent for
        # summary purposes.  For simplicity we store the raw fee in output units.
        fees.append(fee_amount)
        rates.append(effective_rate)

        debug_steps.append({
            "leg": i + 1,
            "side": side,
            "price": price,
            "fee_rate": fee_rate,
            "amount_in": amount_in,
            "raw_out": raw_out,
            "fee_deducted": fee_amount,
            "amount_out": amount_out,
        })

        amount = amount_out

    end_amount = amount
    # Gross profit assumes zero fees
    gross_amount = start_amount
    for leg in legs:
        if leg["side"] == "buy":
            gross_amount = gross_amount / leg["price"] if leg["price"] > 0 else 0.0
        else:
            gross_amount = gross_amount * leg["price"]
    gross_profit = gross_amount - start_amount

    net_profit = end_amount - start_amount
    net_profit_pct = (net_profit / start_amount * 100.0) if start_amount > 0 else 0.0

    total_fees_val = sum(fees)

    # Pad rates/fees to exactly 3 for the dataclass fields
    while len(rates) < 3:
        rates.append(0.0)
    while len(fees) < 3:
        fees.append(0.0)

    return TriangularProfitResult(
        start_amount=start_amount,
        end_amount=end_amount,
        leg1_rate=rates[0],
        leg2_rate=rates[1],
        leg3_rate=rates[2],
        leg1_fee=fees[0],
        leg2_fee=fees[1],
        leg3_fee=fees[2],
        total_fees=total_fees_val,
        gross_profit=gross_profit,
        net_profit=net_profit,
        net_profit_pct=net_profit_pct,
        is_profitable=net_profit > 0,
        implied_rate=implied_rate,
        debug_steps=debug_steps,
    )


def compute_spread(
    best_bid: float,
    best_ask: float,
) -> tuple[float, float]:
    """Compute absolute and percentage spread between bid and ask.

    Parameters
    ----------
    best_bid:
        Highest bid price (across exchanges).
    best_ask:
        Lowest ask price (across exchanges).

    Returns
    -------
    tuple[float, float]
        ``(spread_absolute, spread_pct)`` where ``spread_pct`` is relative
        to the ask.  A positive spread means the bid exceeds the ask
        (arbitrage opportunity).

    Examples
    --------
    >>> compute_spread(102.0, 100.0)
    (2.0, 2.0)
    >>> compute_spread(99.0, 100.0)
    (-1.0, -1.0)
    """
    spread_abs = best_bid - best_ask
    if best_ask > 0:
        spread_pct = spread_abs / best_ask * 100.0
    else:
        spread_pct = 0.0
    return (spread_abs, spread_pct)


def score_opportunity_confidence(
    net_profit_pct: float,
    buy_depth_filled: bool,
    sell_depth_filled: bool,
    data_age_ms: int,
    spread_stability: float = 1.0,
) -> float:
    """Score an arbitrage opportunity from 0 to 100.

    The score blends four factors:

    1. **Profitability** (0-40 pts): higher ``net_profit_pct`` is better,
       with diminishing returns above 1 %.
    2. **Depth sufficiency** (0-20 pts): full fills on both sides score
       highest.
    3. **Data freshness** (0-20 pts): data older than 5 s gets penalised
       sharply.
    4. **Spread stability** (0-20 pts): linear mapping of the 0-1 input.

    Parameters
    ----------
    net_profit_pct:
        Expected net profit as a percentage (e.g. 0.5 for 0.5 %).
    buy_depth_filled:
        Whether the buy side can be fully filled.
    sell_depth_filled:
        Whether the sell side can be fully filled.
    data_age_ms:
        Age of the most recent market-data snapshot in milliseconds.
    spread_stability:
        Stability metric between 0 (volatile) and 1 (rock-steady).

    Returns
    -------
    float
        Confidence score in [0, 100].

    Examples
    --------
    >>> score_opportunity_confidence(0.5, True, True, 200, 0.9)
    ... # a decent opportunity with fresh data
    >>> score_opportunity_confidence(0.1, False, True, 6000, 0.3)
    ... # weak opportunity with stale data
    """
    # 1. Profitability: 0-40 points
    #    Uses a log-like curve: 40 * min(profit_pct / 1.0, 1.0)**0.5
    #    so that 0.25% already scores ~20 pts, 1% saturates at 40.
    if net_profit_pct <= 0:
        profit_score = 0.0
    else:
        clamped = min(net_profit_pct / 1.0, 1.0)
        profit_score = 40.0 * math.sqrt(clamped)

    # 2. Depth sufficiency: 0-20 points
    depth_score = 0.0
    if buy_depth_filled:
        depth_score += 10.0
    if sell_depth_filled:
        depth_score += 10.0

    # 3. Data freshness: 0-20 points
    #    Full score if < 500 ms, linear decay to 0 at 5000 ms, 0 beyond.
    if data_age_ms <= 500:
        freshness_score = 20.0
    elif data_age_ms >= 5000:
        freshness_score = 0.0
    else:
        freshness_score = 20.0 * (1.0 - (data_age_ms - 500) / 4500.0)

    # 4. Spread stability: 0-20 points (linear)
    stability_clamped = max(0.0, min(spread_stability, 1.0))
    stability_score = 20.0 * stability_clamped

    total = profit_score + depth_score + freshness_score + stability_score
    return max(0.0, min(total, 100.0))
