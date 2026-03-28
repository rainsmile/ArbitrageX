"""
Binance exchange adapter.

Implements the full BaseExchangeAdapter interface against the Binance
Spot REST API v3 and WebSocket streams.

REST base : https://api.binance.com
WS base   : wss://stream.binance.com:9443/ws
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from app.core.exceptions import (
    ExchangeAuthError,
    ExchangeError,
    ExchangeNetworkError,
    ExchangeRateLimitError,
)
from app.core.exchange_errors import (
    classify_binance_error,
    ExchangeError as ClassifiedExchangeError,
    ExchangeErrorType,
)
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

_STATUS_MAP: dict[str, OrderStatus] = {
    "NEW": OrderStatus.NEW,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
    "EXPIRED_IN_MATCH": OrderStatus.EXPIRED,
}

_SIDE_MAP: dict[str, OrderSide] = {
    "BUY": OrderSide.BUY,
    "SELL": OrderSide.SELL,
}


class BinanceAdapter(BaseExchangeAdapter):
    """Production adapter for Binance Spot."""

    REST_BASE = "https://api.binance.com"
    WS_BASE = "wss://stream.binance.com:9443/ws"
    TESTNET_REST = "https://testnet.binance.vision"
    TESTNET_WS = "wss://testnet.binance.vision/ws"

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False,
        recv_window: int = 5000,
    ):
        super().__init__("binance", api_key=api_key, api_secret=api_secret)
        self._testnet = testnet
        self._recv_window = recv_window
        self._rest_base = self.TESTNET_REST if testnet else self.REST_BASE
        self._ws_base = self.TESTNET_WS if testnet else self.WS_BASE
        self._client: Optional[httpx.AsyncClient] = None
        self._symbols_cache: dict[str, SymbolInfo] = {}
        self._rate_limit_remaining: int = 1200
        self._rate_limit_reset: float = 0.0
        self._ws_connections: list[Any] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._rest_base,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"X-MBX-APIKEY": self._api_key} if self._api_key else {},
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        # Pre-load symbol list
        try:
            await self.get_symbols()
        except Exception:
            logger.warning("binance: failed to pre-load symbols during init")
        self._initialized = True
        logger.info("binance: adapter initialised (testnet={})", self._testnet)

    async def shutdown(self) -> None:
        await self.unsubscribe_all()
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("binance: adapter shut down")

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add ``timestamp``, ``recvWindow`` and ``signature`` to *params*."""
        if not self._api_secret:
            raise ExchangeAuthError(exchange="binance")
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self._recv_window
        query = urlencode(params)
        sig = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        return params

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        signed: bool = False,
        max_retries: int = 3,
    ) -> Any:
        assert self._client is not None, "Adapter not initialised"
        params = dict(params) if params else {}
        if signed:
            params = self._sign(params)

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                # Rate-limit back-off
                if self._rate_limit_remaining <= 5:
                    wait = max(0.0, self._rate_limit_reset - time.time())
                    if wait > 0:
                        logger.warning("binance: rate-limit back-off {:.1f}s", wait)
                        await asyncio.sleep(wait)

                logger.debug("binance: {} {} params={}", method, path, params)
                resp = await self._client.request(method, path, params=params)

                # Track rate limits from response headers
                used = resp.headers.get("x-mbx-used-weight-1m")
                if used is not None:
                    self._rate_limit_remaining = max(0, 1200 - int(used))

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "5"))
                    self._rate_limit_reset = time.time() + retry_after
                    raise ExchangeRateLimitError(exchange="binance", retry_after=retry_after)

                if resp.status_code == 418:
                    # IP banned
                    raise ExchangeRateLimitError(
                        exchange="binance", retry_after=120.0
                    )

                data = resp.json()

                if resp.status_code >= 400:
                    code = data.get("code", -1)
                    msg = data.get("msg", "unknown error")
                    if code in (-2015, -2014, -1022):
                        raise ExchangeAuthError(exchange="binance")
                    # Classify the error for circuit breaker integration
                    classified = classify_binance_error(resp.status_code, code, msg)
                    exc = ExchangeError(
                        f"binance API error {code}: {msg}",
                        exchange="binance",
                        details={"api_code": code, "api_msg": msg, "classified_type": classified.value},
                    )
                    exc.classified_type = classified
                    exc.is_retryable = classified in (ExchangeErrorType.NETWORK_ERROR, ExchangeErrorType.TIMEOUT_ERROR, ExchangeErrorType.RATE_LIMIT_ERROR)
                    exc.should_circuit_break = classified in (ExchangeErrorType.AUTH_ERROR, ExchangeErrorType.PERMISSION_ERROR, ExchangeErrorType.EXCHANGE_MAINTENANCE, ExchangeErrorType.TIME_SYNC_ERROR)
                    logger.warning("binance: classified error type={} retryable={} circuit_break={}", classified.value, exc.is_retryable, exc.should_circuit_break)
                    raise exc

                return data

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                logger.warning(
                    "binance: network error on attempt {}/{}: {}", attempt, max_retries, exc
                )
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))
            except (ExchangeRateLimitError,) as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(exc.retry_after or 5)
                else:
                    raise

        raise ExchangeNetworkError(exchange="binance") from last_exc

    # ------------------------------------------------------------------
    # Error classification helpers
    # ------------------------------------------------------------------

    def _classify_and_raise(
        self, http_status: int, error_code: int, message: str,
    ) -> ExchangeError:
        """Classify a Binance error and return an ExchangeError with classification metadata."""
        classified = classify_binance_error(http_status, error_code, message)
        exc = ExchangeError(
            f"binance API error {error_code}: {message}",
            exchange="binance",
            details={
                "api_code": error_code,
                "api_msg": message,
                "http_status": http_status,
                "classified_type": classified.value,
            },
        )
        exc.classified_type = classified
        exc.is_retryable = classified in (
            ExchangeErrorType.NETWORK_ERROR,
            ExchangeErrorType.TIMEOUT_ERROR,
            ExchangeErrorType.RATE_LIMIT_ERROR,
        )
        exc.should_circuit_break = classified in (
            ExchangeErrorType.AUTH_ERROR,
            ExchangeErrorType.PERMISSION_ERROR,
            ExchangeErrorType.EXCHANGE_MAINTENANCE,
            ExchangeErrorType.TIME_SYNC_ERROR,
        )
        logger.warning(
            "binance: classified error type={} retryable={} circuit_break={}",
            classified.value, exc.is_retryable, exc.should_circuit_break,
        )
        return exc

    async def _handle_request_error(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        signed: bool = False,
        max_retries: int = 3,
    ) -> Any:
        """Wrapper around _request that handles classified errors with retry and circuit breaker logic."""
        for attempt in range(1, max_retries + 1):
            try:
                return await self._request(method, path, params=params, signed=signed, max_retries=1)
            except ExchangeError as exc:
                classified_type = getattr(exc, "classified_type", None)
                if classified_type is None:
                    raise
                is_retryable = getattr(exc, "is_retryable", False)
                should_cb = getattr(exc, "should_circuit_break", False)
                if should_cb:
                    logger.critical(
                        "binance: circuit-break condition detected type={} -- halting retries",
                        classified_type.value,
                    )
                    raise
                if is_retryable and attempt < max_retries:
                    wait = min(2 ** attempt, 10)
                    logger.info("binance: retryable error, attempt {}/{} backoff={}s", attempt, max_retries, wait)
                    await asyncio.sleep(wait)
                    continue
                raise

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_exchange_info(self) -> ExchangeInfo:
        data = await self._request("GET", "/api/v3/exchangeInfo")
        return ExchangeInfo(
            name="binance",
            display_name="Binance",
            is_connected=True,
            server_time=datetime.fromtimestamp(data["serverTime"] / 1000, tz=timezone.utc),
            rate_limits={
                rl["rateLimitType"]: {"interval": rl["interval"], "limit": rl["intervalNum"]}
                for rl in data.get("rateLimits", [])
            },
        )

    async def get_symbols(self) -> list[SymbolInfo]:
        data = await self._request("GET", "/api/v3/exchangeInfo")
        results: list[SymbolInfo] = []
        for s in data.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            # Extract filters
            price_filter = next((f for f in s.get("filters", []) if f["filterType"] == "PRICE_FILTER"), {})
            lot_filter = next((f for f in s.get("filters", []) if f["filterType"] == "LOT_SIZE"), {})
            notional_filter = next(
                (f for f in s.get("filters", []) if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL")), {}
            )

            base = s["baseAsset"]
            quote = s["quoteAsset"]
            unified = f"{base}/{quote}"

            info = SymbolInfo(
                symbol=unified,
                base_asset=base,
                quote_asset=quote,
                price_precision=s.get("quotePrecision", 8),
                quantity_precision=s.get("baseAssetPrecision", 8),
                min_quantity=float(lot_filter.get("minQty", 0)),
                max_quantity=float(lot_filter.get("maxQty", 0)),
                min_notional=float(notional_filter.get("minNotional", 0)),
                tick_size=float(price_filter.get("tickSize", 0)),
                step_size=float(lot_filter.get("stepSize", 0)),
                is_active=True,
                exchange_symbol=s["symbol"],
            )
            self._symbols_cache[unified] = info
            results.append(info)
        return results

    async def get_ticker(self, symbol: str) -> StandardTicker:
        ex_sym = self._to_exchange_symbol(symbol)
        data = await self._request("GET", "/api/v3/ticker/bookTicker", params={"symbol": ex_sym})
        return StandardTicker(
            exchange="binance",
            symbol=symbol,
            bid=float(data["bidPrice"]),
            ask=float(data["askPrice"]),
            bid_size=float(data["bidQty"]),
            ask_size=float(data["askQty"]),
        )

    async def get_tickers(self, symbols: list[str]) -> list[StandardTicker]:
        # Binance supports fetching all book tickers at once
        data = await self._request("GET", "/api/v3/ticker/bookTicker")
        # Build lookup of exchange symbols we care about
        wanted = {self._to_exchange_symbol(s): s for s in symbols}
        results: list[StandardTicker] = []
        for item in data:
            unified = wanted.get(item["symbol"])
            if unified:
                results.append(
                    StandardTicker(
                        exchange="binance",
                        symbol=unified,
                        bid=float(item["bidPrice"]),
                        ask=float(item["askPrice"]),
                        bid_size=float(item["bidQty"]),
                        ask_size=float(item["askQty"]),
                    )
                )
        return results

    async def get_orderbook(self, symbol: str, depth: int = 20) -> StandardOrderbook:
        ex_sym = self._to_exchange_symbol(symbol)
        # Binance valid limits: 5, 10, 20, 50, 100, 500, 1000, 5000
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        limit = min((l for l in valid_limits if l >= depth), default=5000)
        data = await self._request("GET", "/api/v3/depth", params={"symbol": ex_sym, "limit": limit})
        return StandardOrderbook(
            exchange="binance",
            symbol=symbol,
            bids=[OrderbookLevel(price=float(b[0]), quantity=float(b[1])) for b in data.get("bids", [])],
            asks=[OrderbookLevel(price=float(a[0]), quantity=float(a[1])) for a in data.get("asks", [])],
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, StandardBalance]:
        data = await self._request("GET", "/api/v3/account", signed=True)
        result: dict[str, StandardBalance] = {}
        for b in data.get("balances", []):
            free = float(b["free"])
            locked = float(b["locked"])
            if free > 0 or locked > 0:
                result[b["asset"]] = StandardBalance(
                    asset=b["asset"], free=free, locked=locked
                )
        return result

    async def get_fees(self, symbol: str) -> dict[str, float]:
        # Binance returns fees via the account endpoint or tradeFee endpoint
        # Default Binance spot fees without BNB discount
        try:
            data = await self._request(
                "GET", "/api/v3/account", signed=True
            )
            maker = float(data.get("makerCommission", 10)) / 10000
            taker = float(data.get("takerCommission", 10)) / 10000
            return {"maker": maker, "taker": taker}
        except ExchangeAuthError:
            # If not authenticated, return default fees
            return {"maker": 0.001, "taker": 0.001}

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
        ex_sym = self._to_exchange_symbol(symbol)
        params: dict[str, Any] = {
            "symbol": ex_sym,
            "side": side.value,
            "type": order_type.value,
            "quantity": f"{quantity}",
            "newOrderRespType": "FULL",
        }
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ExchangeError("Price required for LIMIT orders", exchange="binance")
            params["price"] = f"{price}"
            params["timeInForce"] = "GTC"

        data = await self._request("POST", "/api/v3/order", params=params, signed=True)
        return self._parse_order(symbol, data)

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        ex_sym = self._to_exchange_symbol(symbol)
        try:
            await self._request(
                "DELETE",
                "/api/v3/order",
                params={"symbol": ex_sym, "orderId": order_id},
                signed=True,
            )
            return True
        except ExchangeError:
            return False

    async def get_order_status(self, symbol: str, order_id: str) -> StandardOrder:
        ex_sym = self._to_exchange_symbol(symbol)
        data = await self._request(
            "GET",
            "/api/v3/order",
            params={"symbol": ex_sym, "orderId": order_id},
            signed=True,
        )
        return self._parse_order(symbol, data)

    def _parse_order(self, symbol: str, data: dict[str, Any]) -> StandardOrder:
        fills = data.get("fills", [])
        total_fee = sum(float(f.get("commission", 0)) for f in fills)
        fee_asset = fills[0].get("commissionAsset", "") if fills else ""
        return StandardOrder(
            exchange="binance",
            symbol=symbol,
            order_id=str(data["orderId"]),
            client_order_id=data.get("clientOrderId", ""),
            side=_SIDE_MAP.get(data["side"], OrderSide.BUY),
            order_type=OrderType.LIMIT if data["type"] == "LIMIT" else OrderType.MARKET,
            price=float(data["price"]) if float(data.get("price", 0)) > 0 else None,
            quantity=float(data["origQty"]),
            filled_quantity=float(data.get("executedQty", 0)),
            avg_fill_price=float(data["cummulativeQuoteQty"]) / float(data["executedQty"])
            if float(data.get("executedQty", 0)) > 0
            else None,
            fee=total_fee,
            fee_asset=fee_asset,
            status=_STATUS_MAP.get(data["status"], OrderStatus.NEW),
            created_at=datetime.fromtimestamp(data.get("transactTime", data.get("time", 0)) / 1000, tz=timezone.utc),
            raw=data,
        )

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def subscribe_tickers(self, symbols: list[str], callback: TickerCallback) -> None:
        streams = [f"{self._to_exchange_symbol(s).lower()}@bookTicker" for s in symbols]
        combined_url = f"{self._ws_base}/{'/'.join(streams)}"
        # Build reverse lookup
        sym_map = {self._to_exchange_symbol(s).upper(): s for s in symbols}

        task = asyncio.create_task(
            self._ws_listen(combined_url, "ticker", callback, sym_map)
        )
        self._ws_tasks.append(task)

    async def subscribe_orderbook(self, symbol: str, callback: OrderbookCallback) -> None:
        stream = f"{self._to_exchange_symbol(symbol).lower()}@depth20@100ms"
        url = f"{self._ws_base}/{stream}"
        sym_map = {self._to_exchange_symbol(symbol).upper(): symbol}
        task = asyncio.create_task(
            self._ws_listen(url, "orderbook", callback, sym_map, target_symbol=symbol)
        )
        self._ws_tasks.append(task)

    async def unsubscribe_all(self) -> None:
        await self._cancel_ws_tasks()
        for ws in self._ws_connections:
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_connections.clear()

    async def _ws_listen(
        self,
        url: str,
        stream_type: str,
        callback: Any,
        sym_map: dict[str, str],
        target_symbol: str = "",
    ) -> None:
        """Internal WebSocket listener with reconnection logic."""
        import json as json_mod

        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            logger.error("binance: 'websockets' package not installed; WS subscriptions disabled")
            return

        reconnect_delay = 1.0
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws_connections.append(ws)
                    reconnect_delay = 1.0
                    logger.info("binance: WS connected to {}", url)
                    async for raw_msg in ws:
                        try:
                            msg = json_mod.loads(raw_msg)
                            if stream_type == "ticker":
                                # bookTicker format
                                data = msg.get("data", msg)
                                unified = sym_map.get(data.get("s", ""), "")
                                if not unified:
                                    continue
                                ticker = StandardTicker(
                                    exchange="binance",
                                    symbol=unified,
                                    bid=float(data["b"]),
                                    ask=float(data["a"]),
                                    bid_size=float(data["B"]),
                                    ask_size=float(data["A"]),
                                )
                                result = callback(ticker)
                                if asyncio.iscoroutine(result):
                                    await result
                            elif stream_type == "orderbook":
                                data = msg.get("data", msg)
                                ob = StandardOrderbook(
                                    exchange="binance",
                                    symbol=target_symbol,
                                    bids=[OrderbookLevel(float(b[0]), float(b[1])) for b in data.get("bids", data.get("b", []))],
                                    asks=[OrderbookLevel(float(a[0]), float(a[1])) for a in data.get("asks", data.get("a", []))],
                                )
                                result = callback(ob)
                                if asyncio.iscoroutine(result):
                                    await result
                        except Exception:
                            logger.exception("binance: error processing WS message")
            except asyncio.CancelledError:
                logger.debug("binance: WS task cancelled")
                return
            except Exception:
                logger.warning("binance: WS disconnected, reconnecting in {:.0f}s", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
