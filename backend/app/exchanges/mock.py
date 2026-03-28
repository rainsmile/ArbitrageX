"""
Mock exchange adapter for testing and paper trading.

Generates realistic market data with configurable price offsets so
multiple MockExchangeAdapter instances can simulate arbitrage
opportunities without any real API keys.

Usage::

    mock_binance = MockExchangeAdapter(
        name="mock_binance",
        price_offset_pct=0.0,
        initial_balances={"BTC": 1.0, "USDT": 100_000.0},
    )
    mock_okx = MockExchangeAdapter(
        name="mock_okx",
        price_offset_pct=0.15,   # 0.15 % higher than base
    )
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from app.exchanges.base import (
    BaseExchangeAdapter,
    ExchangeInfo,
    OrderbookCallback,
    OrderbookLevel,
    OrderSide,
    OrderStatus,
    OrderType,
    StandardBalance,
    StandardOrder,
    StandardOrderbook,
    StandardTicker,
    SymbolInfo,
    TickerCallback,
)

# ---------------------------------------------------------------------------
# Realistic base prices and volatility parameters
# ---------------------------------------------------------------------------

_BASE_PRICES: dict[str, float] = {
    "BTC/USDT": 60_000.0,
    "ETH/USDT": 3_500.0,
    "SOL/USDT": 140.0,
    "XRP/USDT": 0.55,
    "DOGE/USDT": 0.12,
    "ARB/USDT": 1.10,
    "AVAX/USDT": 35.0,
    "MATIC/USDT": 0.70,
}

_SYMBOL_META: dict[str, dict[str, Any]] = {
    "BTC/USDT": {"base": "BTC", "quote": "USDT", "pprc": 2, "qprc": 6, "tick": 0.01, "step": 0.000001, "min_qty": 0.00001, "min_notional": 10.0, "vol_pct": 0.0004},
    "ETH/USDT": {"base": "ETH", "quote": "USDT", "pprc": 2, "qprc": 5, "tick": 0.01, "step": 0.00001, "min_qty": 0.0001, "min_notional": 10.0, "vol_pct": 0.0005},
    "SOL/USDT": {"base": "SOL", "quote": "USDT", "pprc": 3, "qprc": 3, "tick": 0.001, "step": 0.001, "min_qty": 0.01, "min_notional": 5.0, "vol_pct": 0.0008},
    "XRP/USDT": {"base": "XRP", "quote": "USDT", "pprc": 4, "qprc": 1, "tick": 0.0001, "step": 0.1, "min_qty": 1.0, "min_notional": 5.0, "vol_pct": 0.0007},
    "DOGE/USDT": {"base": "DOGE", "quote": "USDT", "pprc": 5, "qprc": 0, "tick": 0.00001, "step": 1.0, "min_qty": 10.0, "min_notional": 5.0, "vol_pct": 0.001},
    "ARB/USDT": {"base": "ARB", "quote": "USDT", "pprc": 4, "qprc": 1, "tick": 0.0001, "step": 0.1, "min_qty": 1.0, "min_notional": 5.0, "vol_pct": 0.0009},
    "AVAX/USDT": {"base": "AVAX", "quote": "USDT", "pprc": 3, "qprc": 2, "tick": 0.001, "step": 0.01, "min_qty": 0.1, "min_notional": 5.0, "vol_pct": 0.0008},
    "MATIC/USDT": {"base": "MATIC", "quote": "USDT", "pprc": 4, "qprc": 1, "tick": 0.0001, "step": 0.1, "min_qty": 1.0, "min_notional": 5.0, "vol_pct": 0.0008},
}


class MockExchangeAdapter(BaseExchangeAdapter):
    """Fully-functional mock exchange for testing and paper trading.

    Parameters
    ----------
    name:
        Instance name (e.g. ``"mock_binance"``).
    price_offset_pct:
        Percentage offset applied to all prices.  Allows two mock
        instances to simulate a persistent spread.  ``0.15`` means
        prices are 0.15 % higher than the shared random walk.
    initial_balances:
        Starting asset balances.
    slippage_bps:
        Simulated slippage in basis points (1 bp = 0.01 %).
    maker_fee:
        Simulated maker fee rate.
    taker_fee:
        Simulated taker fee rate.
    price_update_interval:
        Seconds between random-walk price updates (for WS streams).
    """

    # Class-level shared random walk so multiple instances see correlated
    # prices (before their individual offset is applied).
    _shared_prices: dict[str, float] = {}

    def __init__(
        self,
        name: str = "mock",
        *,
        price_offset_pct: float = 0.0,
        initial_balances: dict[str, float] | None = None,
        slippage_bps: float = 2.0,
        maker_fee: float = 0.001,
        taker_fee: float = 0.001,
        price_update_interval: float = 0.5,
    ):
        super().__init__(name)
        self._price_offset_pct = price_offset_pct
        self._slippage_bps = slippage_bps
        self._maker_fee = maker_fee
        self._taker_fee = taker_fee
        self._price_update_interval = price_update_interval

        # Internal balances
        default_balances = {"BTC": 1.0, "ETH": 10.0, "USDT": 100_000.0, "SOL": 50.0}
        bal_raw = initial_balances if initial_balances is not None else default_balances
        self._balances: dict[str, StandardBalance] = {
            asset: StandardBalance(asset=asset, free=amount, locked=0.0)
            for asset, amount in bal_raw.items()
        }

        # Order tracking
        self._orders: dict[str, StandardOrder] = {}
        self._open_orders: dict[str, StandardOrder] = {}

        # Price state (per instance, derived from shared + offset)
        self._prices: dict[str, float] = {}

        # WS simulation
        self._ticker_callbacks: dict[str, list[TickerCallback]] = {}
        self._orderbook_callbacks: dict[str, list[OrderbookCallback]] = {}
        self._price_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Class-level shared price walk
    # ------------------------------------------------------------------

    @classmethod
    def _init_shared_prices(cls) -> None:
        if not cls._shared_prices:
            for sym, base_price in _BASE_PRICES.items():
                cls._shared_prices[sym] = base_price

    @classmethod
    def _step_shared_prices(cls) -> None:
        """Advance the shared random walk by one tick."""
        for sym in list(cls._shared_prices):
            meta = _SYMBOL_META.get(sym, {})
            vol = meta.get("vol_pct", 0.0005)
            change = random.gauss(0, vol)
            cls._shared_prices[sym] *= 1.0 + change
            # Clamp to prevent drift to nonsensical values
            base = _BASE_PRICES.get(sym, cls._shared_prices[sym])
            cls._shared_prices[sym] = max(base * 0.5, min(base * 2.0, cls._shared_prices[sym]))

    def _get_price(self, symbol: str) -> float:
        """Return the offset-adjusted mid-price for *symbol*."""
        base = self._shared_prices.get(symbol, _BASE_PRICES.get(symbol, 100.0))
        return base * (1.0 + self._price_offset_pct / 100.0)

    def _get_spread(self, symbol: str) -> float:
        """Return a realistic half-spread in absolute price terms."""
        price = self._get_price(symbol)
        # Spread is roughly 1-3 bps of price
        return price * random.uniform(0.0001, 0.0003)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        self._init_shared_prices()
        for sym in _BASE_PRICES:
            self._prices[sym] = self._get_price(sym)
        self._initialized = True
        logger.info("{}: mock adapter initialised (offset={:.2f}%)", self.name, self._price_offset_pct)

    async def shutdown(self) -> None:
        await self.unsubscribe_all()
        self._initialized = False
        logger.info("{}: mock adapter shut down", self.name)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_exchange_info(self) -> ExchangeInfo:
        return ExchangeInfo(
            name=self.name,
            display_name=f"Mock ({self.name})",
            is_connected=True,
            server_time=datetime.now(timezone.utc),
        )

    async def get_symbols(self) -> list[SymbolInfo]:
        results: list[SymbolInfo] = []
        for sym, meta in _SYMBOL_META.items():
            results.append(
                SymbolInfo(
                    symbol=sym,
                    base_asset=meta["base"],
                    quote_asset=meta["quote"],
                    price_precision=meta["pprc"],
                    quantity_precision=meta["qprc"],
                    min_quantity=meta["min_qty"],
                    max_quantity=1_000_000.0,
                    min_notional=meta["min_notional"],
                    tick_size=meta["tick"],
                    step_size=meta["step"],
                    is_active=True,
                    exchange_symbol=sym.replace("/", ""),
                )
            )
        return results

    async def get_ticker(self, symbol: str) -> StandardTicker:
        self._step_shared_prices()
        mid = self._get_price(symbol)
        hs = self._get_spread(symbol)
        bid = mid - hs
        ask = mid + hs
        return StandardTicker(
            exchange=self.name,
            symbol=symbol,
            bid=bid,
            ask=ask,
            bid_size=round(random.uniform(0.1, 5.0), 4),
            ask_size=round(random.uniform(0.1, 5.0), 4),
            last_price=mid + random.uniform(-hs, hs),
            volume_24h=round(random.uniform(1000, 50000), 2),
        )

    async def get_tickers(self, symbols: list[str]) -> list[StandardTicker]:
        self._step_shared_prices()
        return [await self.get_ticker(s) for s in symbols]

    async def get_orderbook(self, symbol: str, depth: int = 20) -> StandardOrderbook:
        self._step_shared_prices()
        mid = self._get_price(symbol)
        meta = _SYMBOL_META.get(symbol, {})
        tick = meta.get("tick", 0.01)

        bids: list[OrderbookLevel] = []
        asks: list[OrderbookLevel] = []

        # Generate realistic levels with decreasing size
        cumulative_spread = self._get_spread(symbol)
        for i in range(depth):
            # Bid levels go down from mid
            bid_price = mid - cumulative_spread - tick * i
            bid_qty = round(random.uniform(0.01, 3.0) * (1.0 + random.expovariate(0.5)), 6)
            bids.append(OrderbookLevel(price=round(bid_price, meta.get("pprc", 2)), quantity=bid_qty))

            # Ask levels go up from mid
            ask_price = mid + cumulative_spread + tick * i
            ask_qty = round(random.uniform(0.01, 3.0) * (1.0 + random.expovariate(0.5)), 6)
            asks.append(OrderbookLevel(price=round(ask_price, meta.get("pprc", 2)), quantity=ask_qty))

        return StandardOrderbook(
            exchange=self.name,
            symbol=symbol,
            bids=bids,
            asks=asks,
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, StandardBalance]:
        return dict(self._balances)

    async def get_fees(self, symbol: str) -> dict[str, float]:
        return {"maker": self._maker_fee, "taker": self._taker_fee}

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
    ) -> StandardOrder:
        order_id = str(uuid.uuid4())[:12]
        meta = _SYMBOL_META.get(symbol, {})
        base_asset = meta.get("base", symbol.split("/")[0])
        quote_asset = meta.get("quote", symbol.split("/")[-1])

        # Validate balance
        if side == OrderSide.BUY:
            required_asset = quote_asset
            exec_price = price if price else self._get_price(symbol) * (1 + self._get_spread(symbol) / self._get_price(symbol))
            required_amount = quantity * exec_price
        else:
            required_asset = base_asset
            required_amount = quantity

        bal = self._balances.get(required_asset)
        if not bal or bal.free < required_amount:
            available = bal.free if bal else 0.0
            from app.core.exceptions import InsufficientBalanceError
            raise InsufficientBalanceError(
                asset=required_asset,
                required=required_amount,
                available=available,
                exchange=self.name,
            )

        # Lock funds
        bal.free -= required_amount
        bal.locked += required_amount

        now = datetime.now(timezone.utc)
        order = StandardOrder(
            exchange=self.name,
            symbol=symbol,
            order_id=order_id,
            client_order_id=f"mock_{order_id}",
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            status=OrderStatus.NEW,
            created_at=now,
            updated_at=now,
        )

        self._orders[order_id] = order
        self._open_orders[order_id] = order

        # For market orders, fill immediately
        if order_type == OrderType.MARKET:
            await self._fill_order(order)
        else:
            # For limit orders, simulate async fill with small delay
            asyncio.create_task(self._maybe_fill_limit(order))

        return order

    async def _fill_order(self, order: StandardOrder, *, network_delay: bool = True) -> None:
        """Simulate filling an order against the mock orderbook."""
        # Simulate network + exchange processing latency (50-300ms)
        if network_delay:
            delay = random.uniform(0.05, 0.30)
            await asyncio.sleep(delay)

        mid = self._get_price(order.symbol)
        spread = self._get_spread(order.symbol)

        # Calculate execution price with slippage
        slippage = mid * (self._slippage_bps / 10000.0) * random.uniform(0.5, 1.5)
        if order.side == OrderSide.BUY:
            fill_price = mid + spread + slippage
        else:
            fill_price = mid - spread - slippage

        # Apply fee
        fee_rate = self._taker_fee if order.order_type == OrderType.MARKET else self._maker_fee
        fee = order.quantity * fill_price * fee_rate

        meta = _SYMBOL_META.get(order.symbol, {})
        base_asset = meta.get("base", order.symbol.split("/")[0])
        quote_asset = meta.get("quote", order.symbol.split("/")[-1])

        # Update balances
        if order.side == OrderSide.BUY:
            # Unlock the quote we reserved and adjust for actual cost
            quote_bal = self._balances.get(quote_asset)
            if quote_bal:
                actual_cost = order.quantity * fill_price + fee
                reserved = order.quantity * (order.price or fill_price)
                quote_bal.locked -= reserved
                # Refund difference or charge extra
                quote_bal.free += max(0, reserved - actual_cost)

            # Credit base asset
            base_bal = self._balances.get(base_asset)
            if base_bal is None:
                base_bal = StandardBalance(asset=base_asset, free=0.0, locked=0.0)
                self._balances[base_asset] = base_bal
            base_bal.free += order.quantity
        else:
            # Selling: unlock and remove base
            base_bal = self._balances.get(base_asset)
            if base_bal:
                base_bal.locked -= order.quantity

            # Credit quote asset
            quote_bal = self._balances.get(quote_asset)
            if quote_bal is None:
                quote_bal = StandardBalance(asset=quote_asset, free=0.0, locked=0.0)
                self._balances[quote_asset] = quote_bal
            quote_bal.free += order.quantity * fill_price - fee

        # Update order
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.fee = fee
        order.fee_asset = quote_asset
        order.status = OrderStatus.FILLED
        order.updated_at = datetime.now(timezone.utc)

        # Remove from open orders
        self._open_orders.pop(order.order_id, None)
        logger.debug(
            "{}: filled {} {} {} @ {:.4f} (fee={:.6f} {})",
            self.name, order.side.value, order.quantity, order.symbol,
            fill_price, fee, quote_asset,
        )

    async def _maybe_fill_limit(self, order: StandardOrder) -> None:
        """Simulate a limit order fill after a random short delay."""
        try:
            delay = random.uniform(0.05, 0.5)
            await asyncio.sleep(delay)
            if order.order_id in self._open_orders:
                # 90 % chance of fill, 10 % stays open
                if random.random() < 0.90:
                    await self._fill_order(order)
        except asyncio.CancelledError:
            pass

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        order = self._open_orders.pop(order_id, None)
        if order is None:
            return False

        meta = _SYMBOL_META.get(symbol, {})
        base_asset = meta.get("base", symbol.split("/")[0])
        quote_asset = meta.get("quote", symbol.split("/")[-1])

        # Unlock reserved funds
        if order.side == OrderSide.BUY:
            quote_bal = self._balances.get(quote_asset)
            if quote_bal:
                reserved = order.quantity * (order.price or self._get_price(symbol))
                quote_bal.locked -= reserved
                quote_bal.free += reserved
        else:
            base_bal = self._balances.get(base_asset)
            if base_bal:
                base_bal.locked -= order.quantity
                base_bal.free += order.quantity

        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(timezone.utc)
        return True

    async def get_order_status(self, symbol: str, order_id: str) -> StandardOrder:
        order = self._orders.get(order_id)
        if order is None:
            from app.core.exceptions import ExchangeError
            raise ExchangeError(f"Order {order_id} not found", exchange=self.name)
        return order

    # ------------------------------------------------------------------
    # WebSocket simulation
    # ------------------------------------------------------------------

    async def subscribe_tickers(self, symbols: list[str], callback: TickerCallback) -> None:
        for s in symbols:
            self._ticker_callbacks.setdefault(s, []).append(callback)
        if self._price_task is None or self._price_task.done():
            self._price_task = asyncio.create_task(self._price_generator())
            self._ws_tasks.append(self._price_task)

    async def subscribe_orderbook(self, symbol: str, callback: OrderbookCallback) -> None:
        self._orderbook_callbacks.setdefault(symbol, []).append(callback)
        if self._price_task is None or self._price_task.done():
            self._price_task = asyncio.create_task(self._price_generator())
            self._ws_tasks.append(self._price_task)

    async def unsubscribe_all(self) -> None:
        self._ticker_callbacks.clear()
        self._orderbook_callbacks.clear()
        await self._cancel_ws_tasks()
        self._price_task = None

    async def _price_generator(self) -> None:
        """Background task that simulates periodic price updates and
        invokes registered callbacks."""
        logger.info("{}: mock price generator started (interval={:.1f}s)", self.name, self._price_update_interval)
        try:
            while True:
                await asyncio.sleep(self._price_update_interval)
                self._step_shared_prices()

                # Fire ticker callbacks
                for symbol, callbacks in list(self._ticker_callbacks.items()):
                    ticker = await self.get_ticker(symbol)
                    for cb in callbacks:
                        try:
                            result = cb(ticker)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            logger.exception("{}: error in ticker callback for {}", self.name, symbol)

                # Fire orderbook callbacks
                for symbol, callbacks in list(self._orderbook_callbacks.items()):
                    ob = await self.get_orderbook(symbol)
                    for cb in callbacks:
                        try:
                            result = cb(ob)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            logger.exception("{}: error in orderbook callback for {}", self.name, symbol)

        except asyncio.CancelledError:
            logger.debug("{}: mock price generator stopped", self.name)

    # ------------------------------------------------------------------
    # Utility: reset state (useful in tests)
    # ------------------------------------------------------------------

    def reset(self, initial_balances: dict[str, float] | None = None) -> None:
        """Reset all orders and optionally re-initialise balances."""
        self._orders.clear()
        self._open_orders.clear()
        if initial_balances is not None:
            self._balances = {
                asset: StandardBalance(asset=asset, free=amount, locked=0.0)
                for asset, amount in initial_balances.items()
            }

    def set_price(self, symbol: str, price: float) -> None:
        """Override the shared price for *symbol* (before offset is applied).

        Useful for syncing mock adapters with real market data.
        """
        MockExchangeAdapter._shared_prices[symbol] = price

    @classmethod
    def reset_shared_prices(cls) -> None:
        """Reset the class-level shared price state (useful between test runs)."""
        cls._shared_prices.clear()
