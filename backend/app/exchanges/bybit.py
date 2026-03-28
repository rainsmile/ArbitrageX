"""
Bybit exchange adapter (V5 Unified API).

Implements BaseExchangeAdapter against the Bybit V5 REST and WebSocket APIs.

REST base : https://api.bybit.com
WS public : wss://stream.bybit.com/v5/public/spot
WS private: wss://stream.bybit.com/v5/private
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json as json_mod
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from loguru import logger

from app.core.exceptions import (
    ExchangeAuthError,
    ExchangeError,
    ExchangeNetworkError,
    ExchangeRateLimitError,
)
from app.core.exchange_errors import (
    classify_bybit_error,
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
    "New": OrderStatus.NEW,
    "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELED,
    "PartiallyFilledCanceled": OrderStatus.CANCELED,
    "Rejected": OrderStatus.REJECTED,
    "Deactivated": OrderStatus.EXPIRED,
}


class BybitAdapter(BaseExchangeAdapter):
    """Production adapter for Bybit Spot (V5 Unified)."""

    REST_BASE = "https://api.bybit.com"
    TESTNET_REST = "https://api-testnet.bybit.com"
    WS_PUBLIC = "wss://stream.bybit.com/v5/public/spot"
    WS_PRIVATE = "wss://stream.bybit.com/v5/private"
    TESTNET_WS_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/spot"
    TESTNET_WS_PRIVATE = "wss://stream-testnet.bybit.com/v5/private"

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False,
        recv_window: int = 5000,
    ):
        super().__init__("bybit", api_key=api_key, api_secret=api_secret)
        self._testnet = testnet
        self._recv_window = recv_window
        self._rest_base = self.TESTNET_REST if testnet else self.REST_BASE
        self._ws_public_url = self.TESTNET_WS_PUBLIC if testnet else self.WS_PUBLIC
        self._ws_private_url = self.TESTNET_WS_PRIVATE if testnet else self.WS_PRIVATE
        self._client: Optional[httpx.AsyncClient] = None
        self._symbols_cache: dict[str, SymbolInfo] = {}
        self._ws_connections: list[Any] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._rest_base,
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        try:
            await self.get_symbols()
        except Exception:
            logger.warning("bybit: failed to pre-load symbols during init")
        self._initialized = True
        logger.info("bybit: adapter initialised (testnet={})", self._testnet)

    async def shutdown(self) -> None:
        await self.unsubscribe_all()
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("bybit: adapter shut down")

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def _sign_params(self, method: str, params: dict[str, Any] | None = None, body: str = "") -> dict[str, str]:
        """Bybit V5 signing: HMAC-SHA256(timestamp + api_key + recv_window + payload)."""
        if not self._api_secret or not self._api_key:
            raise ExchangeAuthError(exchange="bybit")

        timestamp = str(int(time.time() * 1000))
        if method == "GET" and params:
            payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        else:
            payload = body

        sign_str = f"{timestamp}{self._api_key}{self._recv_window}{payload}"
        signature = hmac.new(
            self._api_secret.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()

        return {
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str(self._recv_window),
        }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        signed: bool = False,
        max_retries: int = 3,
    ) -> Any:
        assert self._client is not None, "Adapter not initialised"

        body_str = json_mod.dumps(json_body) if json_body else ""
        extra_headers: dict[str, str] = {"Content-Type": "application/json"}
        if signed:
            extra_headers.update(self._sign_params(method.upper(), params, body_str))

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug("bybit: {} {} params={}", method, path, params)
                if method.upper() == "GET":
                    resp = await self._client.request(method, path, params=params, headers=extra_headers)
                else:
                    resp = await self._client.request(
                        method, path, content=body_str if json_body else None, headers=extra_headers
                    )

                if resp.status_code == 429:
                    raise ExchangeRateLimitError(exchange="bybit", retry_after=5.0)

                data = resp.json()

                ret_code = data.get("retCode", -1)
                if ret_code != 0:
                    ret_msg = data.get("retMsg", "unknown")
                    if ret_code in (10003, 10004, 33004):
                        raise ExchangeAuthError(exchange="bybit")
                    # Classify the error for circuit breaker integration
                    classified = classify_bybit_error(ret_code, ret_msg)
                    exc = ExchangeError(
                        f"bybit API error {ret_code}: {ret_msg}",
                        exchange="bybit",
                        details={"ret_code": ret_code, "ret_msg": ret_msg, "classified_type": classified.value},
                    )
                    exc.classified_type = classified
                    exc.is_retryable = classified in (ExchangeErrorType.NETWORK_ERROR, ExchangeErrorType.TIMEOUT_ERROR, ExchangeErrorType.RATE_LIMIT_ERROR)
                    exc.should_circuit_break = classified in (ExchangeErrorType.AUTH_ERROR, ExchangeErrorType.PERMISSION_ERROR, ExchangeErrorType.EXCHANGE_MAINTENANCE, ExchangeErrorType.TIME_SYNC_ERROR)
                    logger.warning("bybit: classified error type={} retryable={} circuit_break={}", classified.value, exc.is_retryable, exc.should_circuit_break)
                    raise exc
                return data.get("result", data)

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                logger.warning("bybit: network error on attempt {}/{}: {}", attempt, max_retries, exc)
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))
            except ExchangeRateLimitError as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(exc.retry_after or 5)
                else:
                    raise

        raise ExchangeNetworkError(exchange="bybit") from last_exc

    # ------------------------------------------------------------------
    # Error classification helpers
    # ------------------------------------------------------------------

    def _classify_and_raise(self, ret_code: int, ret_msg: str) -> ExchangeError:
        """Classify a Bybit error and return an ExchangeError with classification metadata."""
        classified = classify_bybit_error(ret_code, ret_msg)
        exc = ExchangeError(
            f"bybit API error {ret_code}: {ret_msg}",
            exchange="bybit",
            details={
                "ret_code": ret_code,
                "ret_msg": ret_msg,
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
            "bybit: classified error type={} retryable={} circuit_break={}",
            classified.value, exc.is_retryable, exc.should_circuit_break,
        )
        return exc

    async def _handle_request_error(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        signed: bool = False,
        max_retries: int = 3,
    ) -> Any:
        """Wrapper around _request that handles classified errors with retry and circuit breaker logic."""
        for attempt in range(1, max_retries + 1):
            try:
                return await self._request(method, path, params=params, json_body=json_body, signed=signed, max_retries=1)
            except ExchangeError as exc:
                classified_type = getattr(exc, "classified_type", None)
                if classified_type is None:
                    raise
                is_retryable = getattr(exc, "is_retryable", False)
                should_cb = getattr(exc, "should_circuit_break", False)
                if should_cb:
                    logger.critical(
                        "bybit: circuit-break condition detected type={} -- halting retries",
                        classified_type.value,
                    )
                    raise
                if is_retryable and attempt < max_retries:
                    wait = min(2 ** attempt, 10)
                    logger.info("bybit: retryable error, attempt {}/{} backoff={}s", attempt, max_retries, wait)
                    await asyncio.sleep(wait)
                    continue
                raise

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_exchange_info(self) -> ExchangeInfo:
        data = await self._request("GET", "/v5/market/time")
        server_ts = int(data.get("timeSecond", 0)) or int(data.get("timeNano", 0)) // 10**9
        return ExchangeInfo(
            name="bybit",
            display_name="Bybit",
            is_connected=True,
            server_time=datetime.fromtimestamp(server_ts, tz=timezone.utc) if server_ts else None,
        )

    async def get_symbols(self) -> list[SymbolInfo]:
        data = await self._request(
            "GET", "/v5/market/instruments-info", params={"category": "spot"}
        )
        results: list[SymbolInfo] = []
        for item in data.get("list", []):
            if item.get("status") != "Trading":
                continue
            base = item.get("baseCoin", "")
            quote = item.get("quoteCoin", "")
            unified = f"{base}/{quote}"
            native = item.get("symbol", "")

            lot_filter = item.get("lotSizeFilter", {})
            price_filter = item.get("priceFilter", {})

            tick_size = float(price_filter.get("tickSize", 0))
            step_size = float(lot_filter.get("basePrecision", lot_filter.get("qtyStep", 0)))
            min_qty = float(lot_filter.get("minOrderQty", 0))
            max_qty = float(lot_filter.get("maxOrderQty", 0))

            price_prec = len(price_filter.get("tickSize", "0.01").rstrip("0").split(".")[-1]) if "." in price_filter.get("tickSize", "") else 0
            qty_prec = len(str(step_size).rstrip("0").split(".")[-1]) if "." in str(step_size) else 0

            info = SymbolInfo(
                symbol=unified,
                base_asset=base,
                quote_asset=quote,
                price_precision=price_prec,
                quantity_precision=qty_prec,
                min_quantity=min_qty,
                max_quantity=max_qty,
                min_notional=float(lot_filter.get("minOrderAmt", 0)),
                tick_size=tick_size,
                step_size=step_size,
                is_active=True,
                exchange_symbol=native,
            )
            self._symbols_cache[unified] = info
            results.append(info)
        return results

    async def get_ticker(self, symbol: str) -> StandardTicker:
        ex_sym = self._to_exchange_symbol(symbol)
        data = await self._request(
            "GET", "/v5/market/tickers", params={"category": "spot", "symbol": ex_sym}
        )
        items = data.get("list", [])
        if not items:
            raise ExchangeError(f"No ticker data for {symbol}", exchange="bybit")
        t = items[0]
        return StandardTicker(
            exchange="bybit",
            symbol=symbol,
            bid=float(t.get("bid1Price", 0)),
            ask=float(t.get("ask1Price", 0)),
            bid_size=float(t.get("bid1Size", 0)),
            ask_size=float(t.get("ask1Size", 0)),
            last_price=float(t.get("lastPrice", 0)),
            volume_24h=float(t.get("volume24h", 0)),
        )

    async def get_tickers(self, symbols: list[str]) -> list[StandardTicker]:
        # Bybit returns all spot tickers when no symbol is specified
        data = await self._request(
            "GET", "/v5/market/tickers", params={"category": "spot"}
        )
        wanted = {self._to_exchange_symbol(s): s for s in symbols}
        results: list[StandardTicker] = []
        for t in data.get("list", []):
            unified = wanted.get(t.get("symbol", ""))
            if unified:
                results.append(
                    StandardTicker(
                        exchange="bybit",
                        symbol=unified,
                        bid=float(t.get("bid1Price", 0)),
                        ask=float(t.get("ask1Price", 0)),
                        bid_size=float(t.get("bid1Size", 0)),
                        ask_size=float(t.get("ask1Size", 0)),
                        last_price=float(t.get("lastPrice", 0)),
                        volume_24h=float(t.get("volume24h", 0)),
                    )
                )
        return results

    async def get_orderbook(self, symbol: str, depth: int = 20) -> StandardOrderbook:
        ex_sym = self._to_exchange_symbol(symbol)
        # Bybit valid limits: 1, 25, 50, 100, 200
        valid = [1, 25, 50, 100, 200]
        limit = min((v for v in valid if v >= depth), default=200)
        data = await self._request(
            "GET",
            "/v5/market/orderbook",
            params={"category": "spot", "symbol": ex_sym, "limit": str(limit)},
        )
        ts_str = data.get("ts", "0")
        return StandardOrderbook(
            exchange="bybit",
            symbol=symbol,
            bids=[OrderbookLevel(float(b[0]), float(b[1])) for b in data.get("b", [])],
            asks=[OrderbookLevel(float(a[0]), float(a[1])) for a in data.get("a", [])],
            timestamp=datetime.fromtimestamp(int(ts_str) / 1000, tz=timezone.utc) if ts_str != "0" else datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, StandardBalance]:
        data = await self._request(
            "GET",
            "/v5/account/wallet-balance",
            params={"accountType": "UNIFIED"},
            signed=True,
        )
        result: dict[str, StandardBalance] = {}
        for acct in data.get("list", []):
            for coin in acct.get("coin", []):
                ccy = coin["coin"]
                free = float(coin.get("availableToWithdraw", coin.get("free", 0)))
                locked = float(coin.get("locked", 0))
                wallet_bal = float(coin.get("walletBalance", 0))
                if wallet_bal > 0:
                    result[ccy] = StandardBalance(
                        asset=ccy,
                        free=free,
                        locked=max(0.0, wallet_bal - free),
                    )
        return result

    async def get_fees(self, symbol: str) -> dict[str, float]:
        try:
            data = await self._request(
                "GET",
                "/v5/account/fee-rate",
                params={"category": "spot", "symbol": self._to_exchange_symbol(symbol)},
                signed=True,
            )
            items = data.get("list", [])
            if items:
                fee = items[0]
                return {
                    "maker": abs(float(fee.get("makerFeeRate", 0.001))),
                    "taker": abs(float(fee.get("takerFeeRate", 0.001))),
                }
        except (ExchangeAuthError, ExchangeError):
            pass
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
        body: dict[str, Any] = {
            "category": "spot",
            "symbol": ex_sym,
            "side": "Buy" if side == OrderSide.BUY else "Sell",
            "orderType": "Limit" if order_type == OrderType.LIMIT else "Market",
            "qty": str(quantity),
        }
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ExchangeError("Price required for LIMIT orders", exchange="bybit")
            body["price"] = str(price)
            body["timeInForce"] = "GTC"

        data = await self._request("POST", "/v5/order/create", json_body=body, signed=True)
        return StandardOrder(
            exchange="bybit",
            symbol=symbol,
            order_id=data.get("orderId", ""),
            client_order_id=data.get("orderLinkId", ""),
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            status=OrderStatus.NEW,
            raw=data,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        ex_sym = self._to_exchange_symbol(symbol)
        try:
            await self._request(
                "POST",
                "/v5/order/cancel",
                json_body={"category": "spot", "symbol": ex_sym, "orderId": order_id},
                signed=True,
            )
            return True
        except ExchangeError:
            return False

    async def get_order_status(self, symbol: str, order_id: str) -> StandardOrder:
        ex_sym = self._to_exchange_symbol(symbol)
        data = await self._request(
            "GET",
            "/v5/order/realtime",
            params={"category": "spot", "symbol": ex_sym, "orderId": order_id},
            signed=True,
        )
        items = data.get("list", [])
        if not items:
            raise ExchangeError(f"Order {order_id} not found", exchange="bybit")
        o = items[0]
        filled = float(o.get("cumExecQty", 0))
        avg_px = float(o.get("avgPrice", 0)) if o.get("avgPrice") and float(o.get("avgPrice", 0)) > 0 else None
        cum_fee = float(o.get("cumExecFee", 0))

        return StandardOrder(
            exchange="bybit",
            symbol=symbol,
            order_id=o.get("orderId", order_id),
            client_order_id=o.get("orderLinkId", ""),
            side=OrderSide.BUY if o.get("side") == "Buy" else OrderSide.SELL,
            order_type=OrderType.LIMIT if o.get("orderType") == "Limit" else OrderType.MARKET,
            price=float(o["price"]) if o.get("price") and float(o.get("price", 0)) > 0 else None,
            quantity=float(o.get("qty", 0)),
            filled_quantity=filled,
            avg_fill_price=avg_px,
            fee=abs(cum_fee),
            fee_asset=o.get("feeCurrency", ""),
            status=_STATUS_MAP.get(o.get("orderStatus", ""), OrderStatus.NEW),
            created_at=datetime.fromtimestamp(int(o.get("createdTime", 0)) / 1000, tz=timezone.utc)
            if o.get("createdTime")
            else datetime.now(timezone.utc),
            updated_at=datetime.fromtimestamp(int(o.get("updatedTime", 0)) / 1000, tz=timezone.utc)
            if o.get("updatedTime")
            else datetime.now(timezone.utc),
            raw=o,
        )

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def subscribe_tickers(self, symbols: list[str], callback: TickerCallback) -> None:
        topics = [f"tickers.{self._to_exchange_symbol(s)}" for s in symbols]
        sym_map = {self._to_exchange_symbol(s): s for s in symbols}
        task = asyncio.create_task(
            self._ws_listen(self._ws_public_url, topics, "ticker", callback, sym_map)
        )
        self._ws_tasks.append(task)

    async def subscribe_orderbook(self, symbol: str, callback: OrderbookCallback) -> None:
        ex_sym = self._to_exchange_symbol(symbol)
        topics = [f"orderbook.50.{ex_sym}"]
        sym_map = {ex_sym: symbol}
        task = asyncio.create_task(
            self._ws_listen(self._ws_public_url, topics, "orderbook", callback, sym_map)
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
        topics: list[str],
        stream_type: str,
        callback: Any,
        sym_map: dict[str, str],
    ) -> None:
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            logger.error("bybit: 'websockets' package not installed")
            return

        reconnect_delay = 1.0
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws_connections.append(ws)
                    reconnect_delay = 1.0

                    sub_msg = json_mod.dumps({"op": "subscribe", "args": topics})
                    await ws.send(sub_msg)
                    logger.info("bybit: WS subscribed to {}", topics)

                    async for raw_msg in ws:
                        try:
                            msg = json_mod.loads(raw_msg)

                            # Handle pong / subscription responses
                            if msg.get("op") in ("subscribe", "pong"):
                                continue

                            topic = msg.get("topic", "")
                            data = msg.get("data", {})

                            if stream_type == "ticker" and topic.startswith("tickers."):
                                ex_sym = topic.split(".", 1)[1] if "." in topic else ""
                                unified = sym_map.get(ex_sym, "")
                                if not unified:
                                    continue
                                ticker = StandardTicker(
                                    exchange="bybit",
                                    symbol=unified,
                                    bid=float(data.get("bid1Price", 0)),
                                    ask=float(data.get("ask1Price", 0)),
                                    bid_size=float(data.get("bid1Size", 0)),
                                    ask_size=float(data.get("ask1Size", 0)),
                                    last_price=float(data.get("lastPrice", 0)),
                                    volume_24h=float(data.get("volume24h", 0)),
                                )
                                result = callback(ticker)
                                if asyncio.iscoroutine(result):
                                    await result

                            elif stream_type == "orderbook" and "orderbook" in topic:
                                # topic = "orderbook.50.BTCUSDT"
                                parts = topic.split(".")
                                ex_sym = parts[-1] if len(parts) >= 3 else ""
                                unified = sym_map.get(ex_sym, "")
                                if not unified:
                                    continue
                                ob = StandardOrderbook(
                                    exchange="bybit",
                                    symbol=unified,
                                    bids=[OrderbookLevel(float(b[0]), float(b[1])) for b in data.get("b", [])],
                                    asks=[OrderbookLevel(float(a[0]), float(a[1])) for a in data.get("a", [])],
                                )
                                result = callback(ob)
                                if asyncio.iscoroutine(result):
                                    await result

                        except Exception:
                            logger.exception("bybit: error processing WS message")
            except asyncio.CancelledError:
                return
            except Exception:
                logger.warning("bybit: WS disconnected, reconnecting in {:.0f}s", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
