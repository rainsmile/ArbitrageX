"""
OKX exchange adapter.

Implements BaseExchangeAdapter against the OKX V5 REST and WebSocket APIs.

REST base     : https://www.okx.com
WS public     : wss://ws.okx.com:8443/ws/v5/public
WS private    : wss://ws.okx.com:8443/ws/v5/private
"""

from __future__ import annotations

import asyncio
import base64
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
    classify_okx_error,
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
    "live": OrderStatus.NEW,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "cancelled": OrderStatus.CANCELED,
    "mmp_canceled": OrderStatus.CANCELED,
}


class OKXAdapter(BaseExchangeAdapter):
    """Production adapter for OKX Spot (V5 API)."""

    REST_BASE = "https://www.okx.com"
    WS_PUBLIC = "wss://ws.okx.com:8443/ws/v5/public"
    WS_PRIVATE = "wss://ws.okx.com:8443/ws/v5/private"

    # Simulated trading endpoints
    SIM_REST_BASE = "https://www.okx.com"
    SIM_WS_PUBLIC = "wss://ws.okx.com:8443/ws/v5/public?brokerId=9999"
    SIM_WS_PRIVATE = "wss://ws.okx.com:8443/ws/v5/private?brokerId=9999"

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        simulated: bool = False,
    ):
        super().__init__("okx", api_key=api_key, api_secret=api_secret, passphrase=passphrase)
        self._simulated = simulated
        self._rest_base = self.REST_BASE
        self._ws_public_url = self.SIM_WS_PUBLIC if simulated else self.WS_PUBLIC
        self._ws_private_url = self.SIM_WS_PRIVATE if simulated else self.WS_PRIVATE
        self._client: Optional[httpx.AsyncClient] = None
        self._symbols_cache: dict[str, SymbolInfo] = {}
        self._ws_connections: list[Any] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._simulated:
            headers["x-simulated-trading"] = "1"
        self._client = httpx.AsyncClient(
            base_url=self._rest_base,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers=headers,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        try:
            await self.get_symbols()
        except Exception:
            logger.warning("okx: failed to pre-load symbols during init")
        self._initialized = True
        logger.info("okx: adapter initialised (simulated={})", self._simulated)

    async def shutdown(self) -> None:
        await self.unsubscribe_all()
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("okx: adapter shut down")

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """OKX V5 signature: base64(HMAC-SHA256(timestamp+method+path+body))."""
        if not self._api_secret:
            raise ExchangeAuthError(exchange="okx")
        prehash = f"{timestamp}{method}{path}{body}"
        mac = hmac.new(
            self._api_secret.encode(), prehash.encode(), hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        sig = self._sign(ts, method, path, body)
        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
        }
        if self._simulated:
            headers["x-simulated-trading"] = "1"
        return headers

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

        # Build URL with query params for signing
        if params:
            qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            sign_path = f"{path}?{qs}"
        else:
            sign_path = path

        body_str = json_mod.dumps(json_body) if json_body else ""
        extra_headers: dict[str, str] = {}
        if signed:
            extra_headers = self._auth_headers(method.upper(), sign_path, body_str)

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug("okx: {} {} params={}", method, path, params)
                resp = await self._client.request(
                    method,
                    path,
                    params=params,
                    content=body_str if json_body else None,
                    headers=extra_headers,
                )

                if resp.status_code == 429:
                    raise ExchangeRateLimitError(exchange="okx", retry_after=5.0)

                data = resp.json()

                # OKX wraps responses in {"code": "0", "msg": "", "data": [...]}
                code = data.get("code", "0")
                if code != "0":
                    msg = data.get("msg", "unknown error")
                    if code in ("50111", "50113", "50114"):
                        raise ExchangeAuthError(exchange="okx")
                    # Classify the error for circuit breaker integration
                    classified = classify_okx_error(code, msg)
                    exc = ExchangeError(
                        f"okx API error {code}: {msg}",
                        exchange="okx",
                        details={"api_code": code, "api_msg": msg, "classified_type": classified.value},
                    )
                    exc.classified_type = classified
                    exc.is_retryable = classified in (ExchangeErrorType.NETWORK_ERROR, ExchangeErrorType.TIMEOUT_ERROR, ExchangeErrorType.RATE_LIMIT_ERROR)
                    exc.should_circuit_break = classified in (ExchangeErrorType.AUTH_ERROR, ExchangeErrorType.PERMISSION_ERROR, ExchangeErrorType.EXCHANGE_MAINTENANCE, ExchangeErrorType.TIME_SYNC_ERROR)
                    logger.warning("okx: classified error type={} retryable={} circuit_break={}", classified.value, exc.is_retryable, exc.should_circuit_break)
                    raise exc
                return data.get("data", data)

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                logger.warning("okx: network error on attempt {}/{}: {}", attempt, max_retries, exc)
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))
            except ExchangeRateLimitError as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(exc.retry_after or 5)
                else:
                    raise

        raise ExchangeNetworkError(exchange="okx") from last_exc

    # ------------------------------------------------------------------
    # Error classification helpers
    # ------------------------------------------------------------------

    def _classify_and_raise(self, error_code: str, message: str) -> ExchangeError:
        """Classify an OKX error and return an ExchangeError with classification metadata."""
        classified = classify_okx_error(error_code, message)
        exc = ExchangeError(
            f"okx API error {error_code}: {message}",
            exchange="okx",
            details={
                "api_code": error_code,
                "api_msg": message,
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
            "okx: classified error type={} retryable={} circuit_break={}",
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
                        "okx: circuit-break condition detected type={} -- halting retries",
                        classified_type.value,
                    )
                    raise
                if is_retryable and attempt < max_retries:
                    wait = min(2 ** attempt, 10)
                    logger.info("okx: retryable error, attempt {}/{} backoff={}s", attempt, max_retries, wait)
                    await asyncio.sleep(wait)
                    continue
                raise

    # ------------------------------------------------------------------
    # Symbol helpers
    # ------------------------------------------------------------------

    def _to_exchange_symbol(self, symbol: str) -> str:
        """BTC/USDT -> BTC-USDT (OKX spot instId format)."""
        return symbol.replace("/", "-")

    def _to_unified_symbol(self, inst_id: str) -> str:
        """BTC-USDT -> BTC/USDT."""
        return inst_id.replace("-", "/")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_exchange_info(self) -> ExchangeInfo:
        # OKX doesn't have a dedicated exchange info endpoint; use system status
        return ExchangeInfo(
            name="okx",
            display_name="OKX",
            is_connected=True,
            server_time=datetime.now(timezone.utc),
        )

    async def get_symbols(self) -> list[SymbolInfo]:
        data = await self._request("GET", "/api/v5/public/instruments", params={"instType": "SPOT"})
        results: list[SymbolInfo] = []
        for inst in data:
            if inst.get("state") != "live":
                continue
            inst_id = inst["instId"]  # e.g. "BTC-USDT"
            base = inst.get("baseCcy", "")
            quote = inst.get("quoteCcy", "")
            unified = f"{base}/{quote}"

            tick_size = float(inst.get("tickSz", 0))
            lot_size = float(inst.get("lotSz", 0))
            min_sz = float(inst.get("minSz", 0))

            # Derive precision from tick/lot sizes
            price_prec = len(inst.get("tickSz", "0.00000001").rstrip("0").split(".")[-1]) if "." in inst.get("tickSz", "") else 0
            qty_prec = len(inst.get("lotSz", "0.00000001").rstrip("0").split(".")[-1]) if "." in inst.get("lotSz", "") else 0

            info = SymbolInfo(
                symbol=unified,
                base_asset=base,
                quote_asset=quote,
                price_precision=price_prec,
                quantity_precision=qty_prec,
                min_quantity=min_sz,
                max_quantity=float(inst.get("maxLmtSz", 0)),
                min_notional=0.0,
                tick_size=tick_size,
                step_size=lot_size,
                is_active=True,
                exchange_symbol=inst_id,
            )
            self._symbols_cache[unified] = info
            results.append(info)
        return results

    async def get_ticker(self, symbol: str) -> StandardTicker:
        inst_id = self._to_exchange_symbol(symbol)
        data = await self._request("GET", "/api/v5/market/ticker", params={"instId": inst_id})
        t = data[0]
        return StandardTicker(
            exchange="okx",
            symbol=symbol,
            bid=float(t.get("bidPx", 0)),
            ask=float(t.get("askPx", 0)),
            bid_size=float(t.get("bidSz", 0)),
            ask_size=float(t.get("askSz", 0)),
            last_price=float(t.get("last", 0)),
            volume_24h=float(t.get("vol24h", 0)),
            timestamp=datetime.fromtimestamp(int(t.get("ts", 0)) / 1000, tz=timezone.utc)
            if t.get("ts")
            else datetime.now(timezone.utc),
        )

    async def get_tickers(self, symbols: list[str]) -> list[StandardTicker]:
        data = await self._request("GET", "/api/v5/market/tickers", params={"instType": "SPOT"})
        wanted = {self._to_exchange_symbol(s): s for s in symbols}
        results: list[StandardTicker] = []
        for t in data:
            unified = wanted.get(t.get("instId", ""))
            if unified:
                results.append(
                    StandardTicker(
                        exchange="okx",
                        symbol=unified,
                        bid=float(t.get("bidPx", 0)),
                        ask=float(t.get("askPx", 0)),
                        bid_size=float(t.get("bidSz", 0)),
                        ask_size=float(t.get("askSz", 0)),
                        last_price=float(t.get("last", 0)),
                        volume_24h=float(t.get("vol24h", 0)),
                    )
                )
        return results

    async def get_orderbook(self, symbol: str, depth: int = 20) -> StandardOrderbook:
        inst_id = self._to_exchange_symbol(symbol)
        # OKX valid sz: 1-400 for books, 1-5 for books5
        sz = min(max(depth, 1), 400)
        data = await self._request(
            "GET", "/api/v5/market/books", params={"instId": inst_id, "sz": str(sz)}
        )
        book = data[0] if data else {}
        return StandardOrderbook(
            exchange="okx",
            symbol=symbol,
            bids=[OrderbookLevel(float(b[0]), float(b[1])) for b in book.get("bids", [])],
            asks=[OrderbookLevel(float(a[0]), float(a[1])) for a in book.get("asks", [])],
            timestamp=datetime.fromtimestamp(int(book.get("ts", 0)) / 1000, tz=timezone.utc)
            if book.get("ts")
            else datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, StandardBalance]:
        data = await self._request("GET", "/api/v5/account/balance", signed=True)
        result: dict[str, StandardBalance] = {}
        if not data:
            return result
        account = data[0] if isinstance(data, list) else data
        for detail in account.get("details", []):
            ccy = detail["ccy"]
            avail = float(detail.get("availBal", 0))
            frozen = float(detail.get("frozenBal", 0))
            if avail > 0 or frozen > 0:
                result[ccy] = StandardBalance(asset=ccy, free=avail, locked=frozen)
        return result

    async def get_fees(self, symbol: str) -> dict[str, float]:
        try:
            inst_id = self._to_exchange_symbol(symbol)
            data = await self._request(
                "GET",
                "/api/v5/account/trade-fee",
                params={"instType": "SPOT", "instId": inst_id},
                signed=True,
            )
            if data:
                fee_info = data[0]
                return {
                    "maker": abs(float(fee_info.get("maker", 0.001))),
                    "taker": abs(float(fee_info.get("taker", 0.0015))),
                }
        except (ExchangeAuthError, ExchangeError):
            pass
        return {"maker": 0.001, "taker": 0.0015}

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
        inst_id = self._to_exchange_symbol(symbol)
        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": side.value.lower(),
            "ordType": "limit" if order_type == OrderType.LIMIT else "market",
            "sz": str(quantity),
        }
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ExchangeError("Price required for LIMIT orders", exchange="okx")
            body["px"] = str(price)

        data = await self._request("POST", "/api/v5/trade/order", json_body=body, signed=True)
        order_info = data[0] if data else {}

        if order_info.get("sCode", "0") != "0":
            raise ExchangeError(
                f"okx order rejected: {order_info.get('sMsg', 'unknown')}",
                exchange="okx",
            )

        ord_id = order_info.get("ordId", "")
        return StandardOrder(
            exchange="okx",
            symbol=symbol,
            order_id=ord_id,
            client_order_id=order_info.get("clOrdId", ""),
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            status=OrderStatus.NEW,
            raw=order_info,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        inst_id = self._to_exchange_symbol(symbol)
        try:
            data = await self._request(
                "POST",
                "/api/v5/trade/cancel-order",
                json_body={"instId": inst_id, "ordId": order_id},
                signed=True,
            )
            result = data[0] if data else {}
            return result.get("sCode", "1") == "0"
        except ExchangeError:
            return False

    async def get_order_status(self, symbol: str, order_id: str) -> StandardOrder:
        inst_id = self._to_exchange_symbol(symbol)
        data = await self._request(
            "GET",
            "/api/v5/trade/order",
            params={"instId": inst_id, "ordId": order_id},
            signed=True,
        )
        o = data[0] if data else {}
        filled = float(o.get("accFillSz", 0))
        avg_px = float(o.get("avgPx", 0)) if o.get("avgPx") else None
        fee_val = abs(float(o.get("fee", 0))) if o.get("fee") else 0.0

        return StandardOrder(
            exchange="okx",
            symbol=symbol,
            order_id=o.get("ordId", order_id),
            client_order_id=o.get("clOrdId", ""),
            side=OrderSide.BUY if o.get("side") == "buy" else OrderSide.SELL,
            order_type=OrderType.LIMIT if o.get("ordType") == "limit" else OrderType.MARKET,
            price=float(o["px"]) if o.get("px") and float(o["px"]) > 0 else None,
            quantity=float(o.get("sz", 0)),
            filled_quantity=filled,
            avg_fill_price=avg_px,
            fee=fee_val,
            fee_asset=o.get("feeCcy", ""),
            status=_STATUS_MAP.get(o.get("state", ""), OrderStatus.NEW),
            created_at=datetime.fromtimestamp(int(o.get("cTime", 0)) / 1000, tz=timezone.utc)
            if o.get("cTime")
            else datetime.now(timezone.utc),
            updated_at=datetime.fromtimestamp(int(o.get("uTime", 0)) / 1000, tz=timezone.utc)
            if o.get("uTime")
            else datetime.now(timezone.utc),
            raw=o,
        )

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def subscribe_tickers(self, symbols: list[str], callback: TickerCallback) -> None:
        args = [{"channel": "tickers", "instId": self._to_exchange_symbol(s)} for s in symbols]
        sym_map = {self._to_exchange_symbol(s): s for s in symbols}
        task = asyncio.create_task(
            self._ws_listen(self._ws_public_url, "tickers", args, callback, sym_map)
        )
        self._ws_tasks.append(task)

    async def subscribe_orderbook(self, symbol: str, callback: OrderbookCallback) -> None:
        inst_id = self._to_exchange_symbol(symbol)
        args = [{"channel": "books", "instId": inst_id}]
        sym_map = {inst_id: symbol}
        task = asyncio.create_task(
            self._ws_listen(self._ws_public_url, "books", args, callback, sym_map)
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
        channel: str,
        subscribe_args: list[dict],
        callback: Any,
        sym_map: dict[str, str],
    ) -> None:
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            logger.error("okx: 'websockets' package not installed")
            return

        reconnect_delay = 1.0
        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws_connections.append(ws)
                    reconnect_delay = 1.0

                    # Send subscribe message
                    sub_msg = json_mod.dumps({"op": "subscribe", "args": subscribe_args})
                    await ws.send(sub_msg)
                    logger.info("okx: WS subscribed to {} on {}", channel, url)

                    async for raw_msg in ws:
                        try:
                            msg = json_mod.loads(raw_msg)
                            # Skip event confirmations
                            if "event" in msg:
                                continue
                            arg = msg.get("arg", {})
                            ch = arg.get("channel", "")
                            inst_id = arg.get("instId", "")
                            unified = sym_map.get(inst_id, "")
                            if not unified:
                                continue

                            for item in msg.get("data", []):
                                if ch == "tickers":
                                    ticker = StandardTicker(
                                        exchange="okx",
                                        symbol=unified,
                                        bid=float(item.get("bidPx", 0)),
                                        ask=float(item.get("askPx", 0)),
                                        bid_size=float(item.get("bidSz", 0)),
                                        ask_size=float(item.get("askSz", 0)),
                                        last_price=float(item.get("last", 0)),
                                        volume_24h=float(item.get("vol24h", 0)),
                                    )
                                    result = callback(ticker)
                                    if asyncio.iscoroutine(result):
                                        await result
                                elif ch == "books":
                                    ob = StandardOrderbook(
                                        exchange="okx",
                                        symbol=unified,
                                        bids=[OrderbookLevel(float(b[0]), float(b[1])) for b in item.get("bids", [])],
                                        asks=[OrderbookLevel(float(a[0]), float(a[1])) for a in item.get("asks", [])],
                                    )
                                    result = callback(ob)
                                    if asyncio.iscoroutine(result):
                                        await result
                        except Exception:
                            logger.exception("okx: error processing WS message")
            except asyncio.CancelledError:
                return
            except Exception:
                logger.warning("okx: WS disconnected, reconnecting in {:.0f}s", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
