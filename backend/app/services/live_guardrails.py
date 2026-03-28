"""Live trading guardrails - the safety layer between execution and real exchanges."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.core.config import Settings, settings
from app.core.credentials import CredentialManager, ExchangeCredential
from app.core.events import EventBus, EventType
from app.core.exchange_errors import ExchangeErrorType
from app.core.kill_switch import KillSwitch
from app.core.trading_modes import TradingMode, get_capabilities, is_live_mode, can_place_real_orders
from app.db.redis import RedisClient
from app.services.audit import AuditService
from app.services.market_data import MarketDataService


@dataclass(slots=True)
class PreOrderCheck:
    """Result of a pre-order validation."""
    approved: bool
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rejections(self) -> list[dict]:
        return [c for c in self.checks if not c.get("passed")]

    def to_dict(self) -> dict:
        return {"approved": self.approved, "checks": self.checks, "rejections": self.rejections}


class LiveGuardrails:
    """Central service for live trading safety enforcement."""

    def __init__(
        self,
        kill_switch: KillSwitch,
        credential_manager: CredentialManager,
        event_bus: EventBus,
        redis_client: RedisClient | None,
        audit_service: AuditService | None,
        market_data: MarketDataService | None,
        config: Settings | None = None,
    ) -> None:
        self._kill = kill_switch
        self._creds = credential_manager
        self._bus = event_bus
        self._redis = redis_client
        self._audit = audit_service
        self._market = market_data
        self._cfg = config or settings
        self._mode = TradingMode(self._cfg.live.trading_mode)

    # -- Mode management --

    @property
    def current_mode(self) -> TradingMode:
        return self._mode

    @property
    def capabilities(self):
        return get_capabilities(self._mode)

    async def set_mode(self, mode: TradingMode, changed_by: str = "system") -> dict:
        """Change trading mode with validation and audit."""
        old_mode = self._mode

        # Validate transition
        if is_live_mode(mode):
            if not self._cfg.live.enabled and mode == TradingMode.LIVE:
                return {"success": False, "reason": "LIVE mode not enabled in config (LIVE_ENABLED=false)"}
            if not self._cfg.live.enable_live_small and mode == TradingMode.LIVE_SMALL:
                return {"success": False, "reason": "LIVE_SMALL mode not enabled in config"}

        self._mode = mode
        logger.warning("Trading mode changed: {} -> {} by {}", old_mode, mode, changed_by)

        if self._audit:
            self._audit.log("LIVE_MODE_CHANGED", "system", "mode", f"{old_mode} -> {mode}",
                          {"old_mode": old_mode.value, "new_mode": mode.value, "changed_by": changed_by})

        await self._bus.publish(EventType.LIVE_MODE_CHANGED, {
            "old_mode": old_mode.value, "new_mode": mode.value, "changed_by": changed_by,
        })

        return {"success": True, "old_mode": old_mode.value, "new_mode": mode.value}

    # -- Pre-order validation --

    async def validate_pre_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        strategy_type: str = "",
        execution_id: str = "",
    ) -> PreOrderCheck:
        """Run all pre-order safety checks. Must pass ALL checks to proceed."""
        checks: list[dict[str, Any]] = []

        def _check(name: str, passed: bool, reason: str):
            checks.append({"name": name, "passed": passed, "reason": reason})

        caps = self.capabilities
        notional = quantity * price

        # 1. Mode allows orders
        _check("mode_allows_orders", caps.can_place_orders,
               f"Mode {self._mode.value} {'allows' if caps.can_place_orders else 'forbids'} real orders")

        # 2. Kill switch
        _check("kill_switch_inactive", not self._kill.is_active,
               "Kill switch is ACTIVE - all trading halted" if self._kill.is_active else "Kill switch inactive")

        # 3. Circuit breaker - exchange level
        exch_cb = f"exchange:{exchange}"
        cb_open = self._kill.is_circuit_open(exch_cb)
        _check("exchange_circuit_breaker", not cb_open,
               f"Circuit breaker OPEN for {exchange}" if cb_open else f"Circuit breaker OK for {exchange}")

        # 4. Circuit breaker - symbol level
        sym_cb = f"symbol:{symbol}"
        sym_open = self._kill.is_circuit_open(sym_cb)
        _check("symbol_circuit_breaker", not sym_open,
               f"Circuit breaker OPEN for {symbol}" if sym_open else f"Circuit breaker OK for {symbol}")

        # 5. Circuit breaker - strategy level
        if strategy_type:
            strat_cb = f"strategy:{strategy_type}"
            strat_open = self._kill.is_circuit_open(strat_cb)
            _check("strategy_circuit_breaker", not strat_open,
                   f"Circuit breaker OPEN for strategy {strategy_type}" if strat_open else "Strategy circuit breaker OK")

        # 6. Exchange whitelist
        wl = self._cfg.live.exchange_whitelist
        if wl:
            in_wl = exchange in wl
            _check("exchange_whitelist", in_wl,
                   f"{exchange} {'in' if in_wl else 'NOT in'} exchange whitelist")

        # 7. Symbol whitelist
        sym_wl = self._cfg.live.symbol_whitelist
        if sym_wl:
            in_sym_wl = symbol in sym_wl
            _check("symbol_whitelist", in_sym_wl,
                   f"{symbol} {'in' if in_sym_wl else 'NOT in'} symbol whitelist")

        # 8. Strategy whitelist
        strat_wl = self._cfg.live.strategy_whitelist
        if strat_wl and strategy_type:
            in_strat_wl = strategy_type in strat_wl
            _check("strategy_whitelist", in_strat_wl,
                   f"{strategy_type} {'in' if in_strat_wl else 'NOT in'} strategy whitelist")

        # 9. Credential check
        cred = self._creds.get(exchange)
        has_keys = cred is not None and cred.has_keys
        _check("credentials_available", has_keys,
               f"API keys {'available' if has_keys else 'MISSING'} for {exchange}")

        # 10. Single order notional limit
        if self._mode == TradingMode.LIVE_SMALL:
            max_single = self._cfg.live.live_small_max_single_usdt
        else:
            max_single = self._cfg.live.live_max_single_usdt
        within_limit = notional <= max_single
        _check("single_order_limit", within_limit,
               f"Notional ${notional:.2f} {'<=' if within_limit else '>'} limit ${max_single:.2f}")

        # 11. Daily notional per exchange
        date_key = time.strftime("%Y%m%d")
        if self._redis:
            daily_key = f"live:daily_notional:{exchange}:{date_key}"
            try:
                daily_used = float(await self._redis.client.get(daily_key) or 0)
            except Exception:
                daily_used = 0.0
            max_daily_exch = self._cfg.live.live_max_daily_per_exchange_usdt
            within_daily = (daily_used + notional) <= max_daily_exch
            _check("daily_exchange_limit", within_daily,
                   f"Daily {exchange} ${daily_used + notional:.2f} {'<=' if within_daily else '>'} ${max_daily_exch:.2f}")

        # 12. Daily notional per symbol
        if self._redis:
            sym_daily_key = f"live:daily_notional:{symbol}:{date_key}"
            try:
                sym_daily_used = float(await self._redis.client.get(sym_daily_key) or 0)
            except Exception:
                sym_daily_used = 0.0
            max_daily_sym = self._cfg.live.live_max_daily_per_symbol_usdt
            within_sym_daily = (sym_daily_used + notional) <= max_daily_sym
            _check("daily_symbol_limit", within_sym_daily,
                   f"Daily {symbol} ${sym_daily_used + notional:.2f} {'<=' if within_sym_daily else '>'} ${max_daily_sym:.2f}")

        # 13. Price deviation check
        if self._market:
            ticker = self._market.get_ticker(exchange, symbol)
            if ticker and ticker.bid > 0 and ticker.ask > 0:
                mid = (ticker.bid + ticker.ask) / 2
                deviation = abs(price - mid) / mid * 100 if mid > 0 else 999
                max_dev = self._cfg.live.max_price_deviation_pct
                within_dev = deviation <= max_dev
                _check("price_deviation", within_dev,
                       f"Price deviation {deviation:.3f}% {'<=' if within_dev else '>'} {max_dev}%")
            else:
                _check("price_deviation", False, f"No ticker data available for {exchange}:{symbol}")

        # 14. Market data freshness
        if self._market:
            age = self._market.get_data_age(exchange, symbol)
            max_age = self._cfg.live.max_price_staleness_s
            if age is not None:
                fresh = age <= max_age
                _check("data_freshness", fresh,
                       f"Data age {age:.1f}s {'<=' if fresh else '>'} {max_age}s")
            else:
                _check("data_freshness", False, f"No market data for {exchange}:{symbol}")

        approved = all(c["passed"] for c in checks)
        result = PreOrderCheck(approved=approved, checks=checks)

        # Audit
        if self._audit and is_live_mode(self._mode):
            self._audit.log(
                "PRE_ORDER_CHECK", "order", execution_id or "manual",
                "APPROVED" if approved else "REJECTED",
                {"exchange": exchange, "symbol": symbol, "side": side,
                 "notional": notional, "checks_passed": sum(1 for c in checks if c["passed"]),
                 "checks_total": len(checks), "rejections": [c["name"] for c in result.rejections]},
            )

        return result

    async def record_live_order_notional(self, exchange: str, symbol: str, notional: float) -> None:
        """Record notional value for daily limit tracking."""
        if not self._redis:
            return
        date_key = time.strftime("%Y%m%d")
        ttl = 86400 + 3600  # 25 hours
        try:
            pipe = self._redis.client.pipeline()
            pipe.incrbyfloat(f"live:daily_notional:{exchange}:{date_key}", notional)
            pipe.expire(f"live:daily_notional:{exchange}:{date_key}", ttl)
            pipe.incrbyfloat(f"live:daily_notional:{symbol}:{date_key}", notional)
            pipe.expire(f"live:daily_notional:{symbol}:{date_key}", ttl)
            pipe.incrbyfloat(f"live:daily_notional:total:{date_key}", notional)
            pipe.expire(f"live:daily_notional:total:{date_key}", ttl)
            await pipe.execute()
        except Exception:
            logger.opt(exception=True).warning("Failed to record live order notional")

    # -- Status --

    def get_live_status(self) -> dict[str, Any]:
        caps = self.capabilities
        return {
            "current_mode": self._mode.value,
            "kill_switch_active": self._kill.is_active,
            "can_place_orders": caps.can_place_orders,
            "can_auto_execute": caps.can_auto_execute,
            "live_enabled": self._cfg.live.enabled,
            "live_small_enabled": self._cfg.live.enable_live_small,
            "max_single_order_usdt": caps.max_single_order_usdt,
            "max_daily_notional_usdt": caps.max_daily_notional_usdt,
            "audit_level": caps.audit_level,
            "open_circuit_breakers": len(self._kill.get_open_breakers()),
            "exchange_whitelist": self._cfg.live.exchange_whitelist,
            "symbol_whitelist": self._cfg.live.symbol_whitelist,
        }

    def get_permissions(self) -> dict[str, Any]:
        caps = self.capabilities
        return {
            "mode": self._mode.value,
            "can_read_public_data": caps.can_read_public_data,
            "can_read_account": caps.can_read_account,
            "can_place_orders": caps.can_place_orders,
            "can_cancel_orders": caps.can_cancel_orders,
            "can_auto_execute": caps.can_auto_execute,
            "requires_api_keys": caps.requires_api_keys,
            "requires_trading_permission": caps.requires_trading_permission,
            "credentials": self._creds.get_status_summary(),
        }
