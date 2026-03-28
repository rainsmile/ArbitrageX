"""Live-trading-specific risk rules."""
from __future__ import annotations

from app.services.risk_engine import RiskRule, RiskCheckResult, RiskContext
from app.services.scanner import OpportunityCandidate
from app.core.kill_switch import KillSwitch
from app.core.trading_modes import TradingMode, is_live_mode, can_place_real_orders
from app.core.credentials import CredentialManager
from app.core.config import Settings, settings


class LiveModeEnabledRule(RiskRule):
    """Blocks all execution if live mode is not properly enabled."""
    def __init__(self, config: Settings | None = None):
        super().__init__("live_mode_enabled")
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if not is_live_mode(mode):
            return RiskCheckResult(rule_name=self.name, passed=True, reason=f"Non-live mode ({mode.value}), rule N/A")
        if mode == TradingMode.LIVE and not self._cfg.live.enabled:
            return RiskCheckResult(rule_name=self.name, passed=False, reason="LIVE mode not enabled in configuration")
        if mode == TradingMode.LIVE_SMALL and not self._cfg.live.enable_live_small:
            return RiskCheckResult(rule_name=self.name, passed=False, reason="LIVE_SMALL mode not enabled in configuration")
        return RiskCheckResult(rule_name=self.name, passed=True, reason=f"Live mode {mode.value} is properly enabled")


class TradingPermissionRule(RiskRule):
    """Verifies API credentials have trading permission."""
    def __init__(self, credential_manager: CredentialManager):
        super().__init__("trading_permission")
        self._creds = credential_manager

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        for exch in [opportunity.buy_exchange, opportunity.sell_exchange]:
            if not exch:
                continue
            cred = self._creds.get(exch)
            if not cred or not cred.has_keys:
                return RiskCheckResult(rule_name=self.name, passed=False, reason=f"No API keys for {exch}")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Credentials available for all exchanges")


class KillSwitchActiveRule(RiskRule):
    """Blocks execution if kill switch is active."""
    def __init__(self, kill_switch: KillSwitch):
        super().__init__("kill_switch")
        self._ks = kill_switch

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        if self._ks.is_active:
            status = self._ks.get_status()
            return RiskCheckResult(rule_name=self.name, passed=False,
                                  reason=f"Kill switch active: {status.get('reason', 'unknown')}")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Kill switch inactive")


class CircuitBreakerRule(RiskRule):
    """Blocks execution if relevant circuit breaker is open."""
    def __init__(self, kill_switch: KillSwitch):
        super().__init__("circuit_breaker")
        self._ks = kill_switch

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        scopes = []
        if opportunity.buy_exchange:
            scopes.append(f"exchange:{opportunity.buy_exchange}")
        if opportunity.sell_exchange:
            scopes.append(f"exchange:{opportunity.sell_exchange}")
        scopes.append(f"symbol:{opportunity.symbol}")
        scopes.append(f"strategy:{opportunity.strategy_type}")

        for scope in scopes:
            if self._ks.is_circuit_open(scope):
                return RiskCheckResult(rule_name=self.name, passed=False, reason=f"Circuit breaker open: {scope}")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="All circuit breakers closed")


class ReadOnlyModeBlockRule(RiskRule):
    """Blocks all order placement in read-only mode."""
    def __init__(self, config: Settings | None = None):
        super().__init__("read_only_block")
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if mode == TradingMode.READ_ONLY:
            return RiskCheckResult(rule_name=self.name, passed=False, reason="System is in READ_ONLY mode")
        return RiskCheckResult(rule_name=self.name, passed=True, reason=f"Mode {mode.value} allows execution")


class MaxSingleOrderNotionalLiveRule(RiskRule):
    """Enforce stricter single-order notional limit for live modes."""
    def __init__(self, config: Settings | None = None):
        super().__init__("max_single_notional_live")
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if not is_live_mode(mode):
            return RiskCheckResult(rule_name=self.name, passed=True, reason="Non-live mode, limit N/A")

        value = getattr(opportunity, 'executable_value_usdt', 0) or 0
        limit = self._cfg.live.live_small_max_single_usdt if mode == TradingMode.LIVE_SMALL else self._cfg.live.live_max_single_usdt
        passed = value <= limit
        return RiskCheckResult(rule_name=self.name, passed=passed,
                              reason=f"Order ${value:.2f} {'<=' if passed else '>'} live limit ${limit:.2f}")


class MaxDailyNotionalPerExchangeRule(RiskRule):
    """Limit daily notional per exchange in live mode."""
    def __init__(self, redis_client, config: Settings | None = None):
        super().__init__("max_daily_notional_exchange")
        self._redis = redis_client
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if not is_live_mode(mode):
            return RiskCheckResult(rule_name=self.name, passed=True, reason="Non-live mode")
        import time
        date_key = time.strftime("%Y%m%d")
        limit = self._cfg.live.live_max_daily_per_exchange_usdt
        for exch in [opportunity.buy_exchange, opportunity.sell_exchange]:
            if not exch:
                continue
            try:
                used = float(await self._redis.client.get(f"live:daily_notional:{exch}:{date_key}") or 0)
            except Exception:
                used = 0
            value = getattr(opportunity, 'executable_value_usdt', 0) or 0
            if (used + value) > limit:
                return RiskCheckResult(rule_name=self.name, passed=False,
                                      reason=f"Daily limit for {exch}: ${used + value:.0f} > ${limit:.0f}")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Within daily exchange limits")


class MaxDailyNotionalPerSymbolRule(RiskRule):
    """Limit daily notional per symbol in live mode."""
    def __init__(self, redis_client, config: Settings | None = None):
        super().__init__("max_daily_notional_symbol")
        self._redis = redis_client
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if not is_live_mode(mode):
            return RiskCheckResult(rule_name=self.name, passed=True, reason="Non-live mode")
        import time
        date_key = time.strftime("%Y%m%d")
        limit = self._cfg.live.live_max_daily_per_symbol_usdt
        sym = opportunity.symbol
        try:
            used = float(await self._redis.client.get(f"live:daily_notional:{sym}:{date_key}") or 0)
        except Exception:
            used = 0
        value = getattr(opportunity, 'executable_value_usdt', 0) or 0
        passed = (used + value) <= limit
        return RiskCheckResult(rule_name=self.name, passed=passed,
                              reason=f"Daily {sym}: ${used + value:.0f} {'<=' if passed else '>'} ${limit:.0f}")


class MaxDailyLiveLossRule(RiskRule):
    """Stricter daily loss limit for live modes."""
    def __init__(self, redis_client, config: Settings | None = None):
        super().__init__("max_daily_live_loss")
        self._redis = redis_client
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if not is_live_mode(mode):
            return RiskCheckResult(rule_name=self.name, passed=True, reason="Non-live mode")
        import time
        date_key = time.strftime("%Y%m%d")
        limit = self._cfg.live.live_max_daily_loss_usdt
        try:
            loss = float(await self._redis.client.get(f"live:daily_loss:{date_key}") or 0)
        except Exception:
            loss = 0
        passed = loss < limit
        return RiskCheckResult(rule_name=self.name, passed=passed,
                              reason=f"Daily live loss ${abs(loss):.2f} {'<' if passed else '>='} limit ${limit:.2f}")


class MaxPriceDeviationRule(RiskRule):
    """Block orders with excessive price deviation from market mid."""
    def __init__(self, market_data, config: Settings | None = None):
        super().__init__("max_price_deviation")
        self._market = market_data
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        max_dev = self._cfg.live.max_price_deviation_pct
        buy_price = opportunity.buy_price
        sell_price = opportunity.sell_price

        for exch, price in [(opportunity.buy_exchange, buy_price), (opportunity.sell_exchange, sell_price)]:
            if not exch or not price:
                continue
            ticker = self._market.get_ticker(exch, opportunity.symbol)
            if not ticker or ticker.bid <= 0:
                continue
            mid = (ticker.bid + ticker.ask) / 2
            if mid > 0:
                dev = abs(price - mid) / mid * 100
                if dev > max_dev:
                    return RiskCheckResult(rule_name=self.name, passed=False,
                                          reason=f"Price deviation {dev:.2f}% on {exch} exceeds {max_dev}%")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Price deviation within limits")


class ExchangeWhitelistRule(RiskRule):
    """Only allow execution on whitelisted exchanges in live mode."""
    def __init__(self, config: Settings | None = None):
        super().__init__("exchange_whitelist_live")
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        wl = self._cfg.live.exchange_whitelist
        if not wl:
            return RiskCheckResult(rule_name=self.name, passed=True, reason="No exchange whitelist configured")
        for exch in [opportunity.buy_exchange, opportunity.sell_exchange]:
            if exch and exch not in wl:
                return RiskCheckResult(rule_name=self.name, passed=False,
                                      reason=f"Exchange {exch} not in live whitelist: {wl}")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Exchanges in whitelist")


class StrategyWhitelistRule(RiskRule):
    """Only allow whitelisted strategies in live mode."""
    def __init__(self, config: Settings | None = None):
        super().__init__("strategy_whitelist_live")
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        wl = self._cfg.live.strategy_whitelist
        if not wl:
            return RiskCheckResult(rule_name=self.name, passed=True, reason="No strategy whitelist")
        if opportunity.strategy_type not in wl:
            return RiskCheckResult(rule_name=self.name, passed=False,
                                  reason=f"Strategy {opportunity.strategy_type} not in whitelist: {wl}")
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Strategy in whitelist")


class MaxOpenExposureLiveRule(RiskRule):
    """Limit total open exposure in live mode."""
    def __init__(self, redis_client, config: Settings | None = None):
        super().__init__("max_open_exposure_live")
        self._redis = redis_client
        self._cfg = config or settings

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        mode = TradingMode(self._cfg.live.trading_mode)
        if not is_live_mode(mode):
            return RiskCheckResult(rule_name=self.name, passed=True, reason="Non-live mode")
        limit = self._cfg.live.live_max_open_exposure_usdt
        # Use context exposure if available
        exposure = sum(context.exchange_exposure.values()) if context and context.exchange_exposure else 0
        value = getattr(opportunity, 'executable_value_usdt', 0) or 0
        passed = (exposure + value) <= limit
        return RiskCheckResult(rule_name=self.name, passed=passed,
                              reason=f"Exposure ${exposure + value:.0f} {'<=' if passed else '>'} ${limit:.0f}")


# Convenience list of all live rules
ALL_LIVE_RULES = [
    LiveModeEnabledRule,
    TradingPermissionRule,
    KillSwitchActiveRule,
    CircuitBreakerRule,
    ReadOnlyModeBlockRule,
    MaxSingleOrderNotionalLiveRule,
    MaxDailyNotionalPerExchangeRule,
    MaxDailyNotionalPerSymbolRule,
    MaxDailyLiveLossRule,
    MaxPriceDeviationRule,
    ExchangeWhitelistRule,
    StrategyWhitelistRule,
    MaxOpenExposureLiveRule,
]
