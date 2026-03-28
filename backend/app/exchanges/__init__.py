"""
Exchange adapter layer.

Public API
----------
- ``BaseExchangeAdapter`` — abstract interface all adapters implement
- ``BinanceAdapter``, ``OKXAdapter``, ``BybitAdapter`` — production adapters
- ``MockExchangeAdapter`` — testing / paper-trading adapter
- ``ExchangeFactory`` — creates and manages adapter lifecycle

Standardised data classes (defined in ``base``):
    ExchangeInfo, SymbolInfo, StandardTicker, StandardOrderbook,
    OrderbookLevel, StandardBalance, StandardOrder, OrderSide,
    OrderType, OrderStatus
"""

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
from app.exchanges.binance import BinanceAdapter
from app.exchanges.bybit import BybitAdapter
from app.exchanges.factory import ExchangeFactory
from app.exchanges.mock import MockExchangeAdapter
from app.exchanges.okx import OKXAdapter

__all__ = [
    # Base & data classes
    "BaseExchangeAdapter",
    "ExchangeInfo",
    "OrderbookCallback",
    "OrderbookLevel",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "StandardBalance",
    "StandardOrder",
    "StandardOrderbook",
    "StandardTicker",
    "SymbolInfo",
    "TickerCallback",
    # Adapters
    "BinanceAdapter",
    "OKXAdapter",
    "BybitAdapter",
    "MockExchangeAdapter",
    # Factory
    "ExchangeFactory",
]
