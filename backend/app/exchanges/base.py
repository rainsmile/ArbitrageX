"""
Abstract base class for exchange adapters and standardized data structures.

Every exchange adapter (Binance, OKX, Bybit, Mock) must subclass
``BaseExchangeAdapter`` and implement all abstract methods.  The adapter
layer translates exchange-specific wire formats into the standardized
dataclasses defined here so the rest of the system never touches raw
exchange responses.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# ---------------------------------------------------------------------------
# Standardized data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ExchangeInfo:
    """High-level exchange metadata."""
    name: str
    display_name: str
    is_connected: bool = False
    server_time: Optional[datetime] = None
    rate_limits: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SymbolInfo:
    """Normalised trading pair information."""
    symbol: str                     # unified, e.g. "BTC/USDT"
    base_asset: str                 # e.g. "BTC"
    quote_asset: str                # e.g. "USDT"
    price_precision: int = 8
    quantity_precision: int = 8
    min_quantity: float = 0.0
    max_quantity: float = 0.0
    min_notional: float = 0.0
    tick_size: float = 0.0
    step_size: float = 0.0
    is_active: bool = True
    exchange_symbol: str = ""       # native symbol on the exchange, e.g. "BTCUSDT"


@dataclass(slots=True)
class StandardTicker:
    """Best-bid/ask snapshot."""
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    last_price: float = 0.0
    volume_24h: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class OrderbookLevel:
    price: float
    quantity: float


@dataclass(slots=True)
class StandardOrderbook:
    """Normalised L2 orderbook snapshot."""
    exchange: str
    symbol: str
    bids: list[OrderbookLevel] = field(default_factory=list)
    asks: list[OrderbookLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid

    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return 0.0


@dataclass(slots=True)
class StandardBalance:
    """Per-asset balance."""
    asset: str
    free: float = 0.0
    locked: float = 0.0

    @property
    def total(self) -> float:
        return self.free + self.locked


@dataclass(slots=True)
class StandardOrder:
    """Normalised order."""
    exchange: str
    symbol: str
    order_id: str
    client_order_id: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: Optional[float] = None
    quantity: float = 0.0
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    fee: float = 0.0
    fee_asset: str = ""
    status: OrderStatus = OrderStatus.NEW
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = field(default_factory=dict)


# Type alias for WS callbacks
TickerCallback = Callable[[StandardTicker], Coroutine[Any, Any, None] | None]
OrderbookCallback = Callable[[StandardOrderbook], Coroutine[Any, Any, None] | None]


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class BaseExchangeAdapter(ABC):
    """Abstract interface that every exchange adapter must implement.

    Subclasses handle the specifics of authentication, serialisation,
    rate-limiting and websocket management for a particular exchange.
    """

    def __init__(self, name: str, *, api_key: str = "", api_secret: str = "", passphrase: str = ""):
        self.name = name
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._initialized = False
        self._ws_tasks: list[asyncio.Task] = []

    # -- lifecycle -----------------------------------------------------------

    @abstractmethod
    async def initialize(self) -> None:
        """Set up HTTP clients, load exchange metadata, etc."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully close all connections and cancel background tasks."""

    # -- market data (REST) --------------------------------------------------

    @abstractmethod
    async def get_exchange_info(self) -> ExchangeInfo:
        """Return high-level exchange metadata."""

    @abstractmethod
    async def get_symbols(self) -> list[SymbolInfo]:
        """Return list of all tradeable symbols."""

    @abstractmethod
    async def get_ticker(self, symbol: str) -> StandardTicker:
        """Fetch current best-bid/ask for *symbol* (unified format, e.g. "BTC/USDT")."""

    @abstractmethod
    async def get_tickers(self, symbols: list[str]) -> list[StandardTicker]:
        """Fetch tickers for multiple symbols in a single call where possible."""

    @abstractmethod
    async def get_orderbook(self, symbol: str, depth: int = 20) -> StandardOrderbook:
        """Fetch L2 orderbook up to *depth* levels."""

    # -- account (REST, authenticated) ---------------------------------------

    @abstractmethod
    async def get_balance(self) -> dict[str, StandardBalance]:
        """Return balances keyed by asset symbol."""

    @abstractmethod
    async def get_fees(self, symbol: str) -> dict[str, float]:
        """Return ``{"maker": float, "taker": float}`` fee rates for *symbol*."""

    # -- trading (REST, authenticated) ---------------------------------------

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
    ) -> StandardOrder:
        """Place a new order. Returns the created order."""

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an open order. Returns ``True`` if successfully cancelled."""

    @abstractmethod
    async def get_order_status(self, symbol: str, order_id: str) -> StandardOrder:
        """Query the current state of an order."""

    # -- WebSocket -----------------------------------------------------------

    @abstractmethod
    async def subscribe_tickers(self, symbols: list[str], callback: TickerCallback) -> None:
        """Open a WS connection streaming ticker updates for *symbols*."""

    @abstractmethod
    async def subscribe_orderbook(self, symbol: str, callback: OrderbookCallback) -> None:
        """Open a WS connection streaming orderbook updates for *symbol*."""

    @abstractmethod
    async def unsubscribe_all(self) -> None:
        """Close all active WebSocket subscriptions."""

    # -- helpers -------------------------------------------------------------

    def _to_exchange_symbol(self, symbol: str) -> str:
        """Convert unified symbol ``BTC/USDT`` to exchange-native format.

        Default implementation simply strips the ``/``.  Subclasses may
        override if the exchange uses a different convention.
        """
        return symbol.replace("/", "")

    def _to_unified_symbol(self, exchange_symbol: str) -> str:
        """Inverse of ``_to_exchange_symbol``.

        Default is a no-op; subclasses should override.
        """
        return exchange_symbol

    async def _cancel_ws_tasks(self) -> None:
        """Cancel all background WS tasks."""
        for task in self._ws_tasks:
            if not task.done():
                task.cancel()
        if self._ws_tasks:
            await asyncio.gather(*self._ws_tasks, return_exceptions=True)
        self._ws_tasks.clear()
