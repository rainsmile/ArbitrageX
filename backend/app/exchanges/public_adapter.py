"""
Public market data adapter — fetches real-time ticker data from exchange
public REST APIs.  **No API keys required.**

Supported exchanges (top 10 global by volume):
  binance, okx, bybit, coinbase, kraken, kucoin, gate, htx, bitget, mexc
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
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
# Symbol mapping: unified  →  exchange-native
# ---------------------------------------------------------------------------

# Standard symbols we track
TRACKED_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT",
    "DOT/USDT", "POL/USDT",
]

# Some exchanges still use old ticker names (e.g. Binance uses MATIC instead of POL)
_SYMBOL_ALIASES: dict[str, dict[str, str]] = {
    # All major exchanges now list POL natively; no aliases needed.
}

# Symbols not listed on certain exchanges (skip to avoid query errors)
_EXCHANGE_SKIP: dict[str, set[str]] = {
    "kraken": {"POL/USDT"},
}


def _unified_to_native(symbol: str, exchange: str) -> str:
    """Convert 'BTC/USDT' to exchange-specific format."""
    # Apply alias mapping (e.g. POL→MATIC on Binance)
    alias_map = _SYMBOL_ALIASES.get(exchange, {})
    symbol = alias_map.get(symbol, symbol)
    base, quote = symbol.split("/")
    if exchange in ("binance", "mexc"):
        return f"{base}{quote}"           # BTCUSDT
    if exchange == "okx":
        return f"{base}-{quote}"          # BTC-USDT
    if exchange == "bybit":
        return f"{base}{quote}"           # BTCUSDT
    if exchange == "coinbase":
        return f"{base}-{quote}"          # BTC-USDT
    if exchange == "kraken":
        # Kraken uses non-standard ticker names
        _kraken_base_map = {"BTC": "XBT", "DOGE": "XDG"}
        b = _kraken_base_map.get(base, base)
        return f"{b}{quote}"              # XBTUSDT
    if exchange == "kucoin":
        return f"{base}-{quote}"          # BTC-USDT
    if exchange == "gate":
        return f"{base}_{quote}"          # BTC_USDT
    if exchange == "htx":
        return f"{base.lower()}{quote.lower()}"  # btcusdt
    if exchange == "bitget":
        return f"{base}{quote}"           # BTCUSDT
    return f"{base}{quote}"


# ---------------------------------------------------------------------------
# Per-exchange ticker parsers
# ---------------------------------------------------------------------------

def _parse_binance(data: list[dict], exchange_name: str) -> list[StandardTicker]:
    """Binance GET /api/v3/ticker/24hr"""
    # Build lookup: native_symbol → data
    lookup = {d["symbol"]: d for d in data}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "binance")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("bidPrice", 0)),
            ask=float(d.get("askPrice", 0)),
            bid_size=float(d.get("bidQty", 0)),
            ask_size=float(d.get("askQty", 0)),
            last_price=float(d.get("lastPrice", 0)),
            volume_24h=float(d.get("quoteVolume", 0)),
        ))
    return results


def _parse_okx(data: dict, exchange_name: str) -> list[StandardTicker]:
    """OKX GET /api/v5/market/tickers?instType=SPOT"""
    items = data.get("data", [])
    lookup = {d["instId"]: d for d in items}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "okx")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("bidPx", 0)),
            ask=float(d.get("askPx", 0)),
            bid_size=float(d.get("bidSz", 0)),
            ask_size=float(d.get("askSz", 0)),
            last_price=float(d.get("last", 0)),
            volume_24h=float(d.get("volCcy24h", 0)),
        ))
    return results


def _parse_bybit(data: dict, exchange_name: str) -> list[StandardTicker]:
    """Bybit GET /v5/market/tickers?category=spot"""
    items = data.get("result", {}).get("list", [])
    lookup = {d["symbol"]: d for d in items}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "bybit")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("bid1Price", 0)),
            ask=float(d.get("ask1Price", 0)),
            bid_size=float(d.get("bid1Size", 0)),
            ask_size=float(d.get("ask1Size", 0)),
            last_price=float(d.get("lastPrice", 0)),
            volume_24h=float(d.get("turnover24h", 0)),
        ))
    return results


def _parse_coinbase(data: dict, exchange_name: str) -> list[StandardTicker]:
    """Coinbase Exchange GET /api/v3/brokerage/market/products — or products/ticker"""
    # We fetch individual tickers, data is already per-symbol dict
    if isinstance(data, dict) and "price" in data:
        return []  # handled per-symbol
    return []


def _parse_kraken(data: dict, exchange_name: str) -> list[StandardTicker]:
    """Kraken GET /0/public/Ticker"""
    result = data.get("result", {})
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "kraken")
        # Kraken uses various pair names, try common patterns
        d = result.get(native) or result.get(f"X{native}") or result.get(f"{native}")
        if not d:
            # Try with full kraken naming
            base, quote = sym.split("/")
            b = "XXBT" if base == "BTC" else f"X{base}" if len(base) == 3 else base
            q = f"Z{quote}" if quote in ("USD", "EUR") else quote
            d = result.get(f"{b}{q}")
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d["b"][0]) if "b" in d else 0,
            ask=float(d["a"][0]) if "a" in d else 0,
            bid_size=float(d["b"][2]) if "b" in d else 0,
            ask_size=float(d["a"][2]) if "a" in d else 0,
            last_price=float(d["c"][0]) if "c" in d else 0,
            volume_24h=float(d["v"][1]) if "v" in d else 0,
        ))
    return results


def _parse_kucoin(data: dict, exchange_name: str) -> list[StandardTicker]:
    """KuCoin GET /api/v1/market/allTickers"""
    items = data.get("data", {}).get("ticker", [])
    lookup = {d["symbol"]: d for d in items}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "kucoin")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("buy", 0) or 0),
            ask=float(d.get("sell", 0) or 0),
            last_price=float(d.get("last", 0) or 0),
            volume_24h=float(d.get("volValue", 0) or 0),
        ))
    return results


def _parse_gate(data: list[dict], exchange_name: str) -> list[StandardTicker]:
    """Gate.io GET /api/v4/spot/tickers"""
    lookup = {d["currency_pair"]: d for d in data}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "gate")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("highest_bid", 0) or 0),
            ask=float(d.get("lowest_ask", 0) or 0),
            last_price=float(d.get("last", 0) or 0),
            volume_24h=float(d.get("quote_volume", 0) or 0),
        ))
    return results


def _parse_htx(data: dict, exchange_name: str) -> list[StandardTicker]:
    """HTX (Huobi) GET /market/tickers"""
    items = data.get("data", [])
    lookup = {d["symbol"]: d for d in items}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "htx")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("bid", 0)),
            ask=float(d.get("ask", 0)),
            bid_size=float(d.get("bidSize", 0)),
            ask_size=float(d.get("askSize", 0)),
            last_price=float(d.get("close", 0)),
            volume_24h=float(d.get("vol", 0)),
        ))
    return results


def _parse_bitget(data: dict, exchange_name: str) -> list[StandardTicker]:
    """Bitget GET /api/v2/spot/market/tickers"""
    items = data.get("data", [])
    lookup = {d["symbol"]: d for d in items}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "bitget")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("buyOne", 0) or 0),
            ask=float(d.get("sellOne", 0) or 0),
            last_price=float(d.get("lastPr", 0) or 0),
            volume_24h=float(d.get("quoteVolume", 0) or 0),
        ))
    return results


def _parse_mexc(data: list[dict], exchange_name: str) -> list[StandardTicker]:
    """MEXC GET /api/v3/ticker/24hr"""
    lookup = {d["symbol"]: d for d in data}
    results = []
    for sym in TRACKED_SYMBOLS:
        native = _unified_to_native(sym, "mexc")
        d = lookup.get(native)
        if not d:
            continue
        results.append(StandardTicker(
            exchange=exchange_name,
            symbol=sym,
            bid=float(d.get("bidPrice", 0) or 0),
            ask=float(d.get("askPrice", 0) or 0),
            last_price=float(d.get("lastPrice", 0) or 0),
            volume_24h=float(d.get("quoteVolume", 0) or 0),
        ))
    return results


# ---------------------------------------------------------------------------
# Exchange endpoint registry
# ---------------------------------------------------------------------------

EXCHANGE_ENDPOINTS: dict[str, dict[str, Any]] = {
    "binance": {
        "url": "https://api.binance.com/api/v3/ticker/24hr",
        "parser": _parse_binance,
    },
    "okx": {
        "url": "https://www.okx.com/api/v5/market/tickers?instType=SPOT",
        "parser": _parse_okx,
    },
    "bybit": {
        "url": "https://api.bybit.com/v5/market/tickers?category=spot",
        "parser": _parse_bybit,
    },
    "kraken": {
        "url": "https://api.kraken.com/0/public/Ticker",
        "params": lambda: {"pair": ",".join(
            _unified_to_native(s, "kraken")
            for s in TRACKED_SYMBOLS
            if s not in _EXCHANGE_SKIP.get("kraken", set())
        )},
        "parser": _parse_kraken,
    },
    "kucoin": {
        "url": "https://api.kucoin.com/api/v1/market/allTickers",
        "parser": _parse_kucoin,
    },
    "gate": {
        "url": "https://api.gateio.ws/api/v4/spot/tickers",
        "parser": _parse_gate,
    },
    "htx": {
        "url": "https://api.huobi.pro/market/tickers",
        "parser": _parse_htx,
    },
    "bitget": {
        "url": "https://api.bitget.com/api/v2/spot/market/tickers",
        "parser": _parse_bitget,
    },
    "mexc": {
        "url": "https://api.mexc.com/api/v3/ticker/24hr",
        "parser": _parse_mexc,
    },
}


# ---------------------------------------------------------------------------
# PublicExchangeAdapter
# ---------------------------------------------------------------------------

class PublicExchangeAdapter(BaseExchangeAdapter):
    """Read-only adapter that fetches public market data from a real exchange.

    No API keys needed.  Trading operations raise NotImplementedError.
    """

    def __init__(self, name: str, *, timeout: float = 10.0):
        super().__init__(name)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._cached_tickers: list[StandardTicker] = []
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 2.0  # seconds

    @property
    def _endpoint(self) -> dict[str, Any]:
        return EXCHANGE_ENDPOINTS.get(self.name, {})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": "ArbitrageX/1.0"},
            follow_redirects=True,
        )
        self._initialized = True
        logger.info("{}: public adapter initialised", self.name)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_exchange_info(self) -> ExchangeInfo:
        return ExchangeInfo(
            name=self.name,
            display_name=self.name.upper(),
            is_connected=self._initialized,
            server_time=datetime.now(timezone.utc),
        )

    async def get_symbols(self) -> list[SymbolInfo]:
        return [
            SymbolInfo(
                symbol=sym,
                base_asset=sym.split("/")[0],
                quote_asset=sym.split("/")[1],
                is_active=True,
                exchange_symbol=_unified_to_native(sym, self.name),
            )
            for sym in TRACKED_SYMBOLS
        ]

    async def _fetch_all_tickers(self) -> list[StandardTicker]:
        """Fetch and cache all tickers from the exchange."""
        import time
        now = time.time()
        if now - self._cache_ts < self._cache_ttl and self._cached_tickers:
            return self._cached_tickers

        ep = self._endpoint
        if not ep or not self._client:
            return []

        url = ep["url"]
        params = ep.get("params", lambda: None)()
        parser = ep["parser"]

        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            tickers = parser(data, self.name)
            self._cached_tickers = tickers
            self._cache_ts = now
            return tickers
        except Exception as e:
            logger.warning("{}: failed to fetch tickers: {}", self.name, e)
            return self._cached_tickers  # return stale if available

    async def get_ticker(self, symbol: str) -> StandardTicker:
        tickers = await self._fetch_all_tickers()
        for t in tickers:
            if t.symbol == symbol:
                return t
        # Return empty ticker if not found
        return StandardTicker(exchange=self.name, symbol=symbol, bid=0, ask=0)

    async def get_tickers(self, symbols: list[str]) -> list[StandardTicker]:
        tickers = await self._fetch_all_tickers()
        symbol_set = set(symbols)
        return [t for t in tickers if t.symbol in symbol_set]

    async def get_orderbook(self, symbol: str, depth: int = 20) -> StandardOrderbook:
        # Public orderbook requires per-symbol API call, return empty for now
        return StandardOrderbook(exchange=self.name, symbol=symbol)

    # ------------------------------------------------------------------
    # Account (not supported — read-only adapter)
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, StandardBalance]:
        return {}

    async def get_fees(self, symbol: str) -> dict[str, float]:
        return {"maker": 0.001, "taker": 0.001}

    # ------------------------------------------------------------------
    # Trading (not supported)
    # ------------------------------------------------------------------

    async def place_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                          quantity: float, price: Optional[float] = None) -> StandardOrder:
        raise NotImplementedError(f"{self.name}: public adapter does not support trading")

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        raise NotImplementedError(f"{self.name}: public adapter does not support trading")

    async def get_order_status(self, symbol: str, order_id: str) -> StandardOrder:
        raise NotImplementedError(f"{self.name}: public adapter does not support trading")

    # ------------------------------------------------------------------
    # WebSocket (use polling instead)
    # ------------------------------------------------------------------

    async def subscribe_tickers(self, symbols: list[str], callback: TickerCallback) -> None:
        pass  # Not implemented for public adapter

    async def subscribe_orderbook(self, symbol: str, callback: OrderbookCallback) -> None:
        pass

    async def unsubscribe_all(self) -> None:
        pass
