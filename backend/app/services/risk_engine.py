"""
RiskEngine -- evaluates arbitrage opportunities against a configurable set
of risk rules before execution is allowed.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.db.redis import RedisClient
from app.models.risk import RiskEvent, RiskEventType, RiskSeverity
from app.services.market_data import MarketDataService
from app.services.scanner import OpportunityCandidate


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RiskCheckResult:
    """Result of a single risk rule evaluation."""
    rule_name: str
    passed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RiskDecision:
    """Aggregate decision from all risk rules."""
    approved: bool
    results: list[RiskCheckResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @property
    def violations(self) -> list[RiskCheckResult]:
        return [r for r in self.results if not r.passed]

    @property
    def violation_names(self) -> list[str]:
        return [r.rule_name for r in self.results if not r.passed]


@dataclass
class RiskContext:
    """Runtime context passed to each risk rule alongside the opportunity."""
    balances: dict[str, dict[str, float]] = field(default_factory=dict)
    daily_pnl_usdt: float = 0.0
    consecutive_failures: int = 0
    concurrent_executions: int = 0
    exchange_exposure: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract rule
# ---------------------------------------------------------------------------

class RiskRule(ABC):
    """Base class for all risk rules."""

    def __init__(self, name: str, *, enabled: bool = True) -> None:
        self.name = name
        self.enabled = enabled

    @abstractmethod
    async def check(
        self,
        opportunity: OpportunityCandidate,
        context: RiskContext,
    ) -> RiskCheckResult:
        ...


# ---------------------------------------------------------------------------
# Concrete rules
# ---------------------------------------------------------------------------

class MaxOrderValueRule(RiskRule):
    def __init__(self, max_value_usdt: float, **kwargs: Any) -> None:
        super().__init__("max_order_value", **kwargs)
        self.max_value_usdt = max_value_usdt

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        value = opportunity.executable_value_usdt
        passed = value <= self.max_value_usdt
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else f"Order value {value:.2f} exceeds limit {self.max_value_usdt:.2f}",
            details={"order_value": value, "limit": self.max_value_usdt},
        )


class MaxDailyLossRule(RiskRule):
    def __init__(self, max_loss_usdt: float, redis_client: RedisClient, **kwargs: Any) -> None:
        super().__init__("max_daily_loss", **kwargs)
        self.max_loss_usdt = max_loss_usdt
        self._redis = redis_client

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        # Read daily loss from Redis
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        redis_key = f"risk:daily_loss:{today}"
        try:
            raw = await self._redis.get(redis_key)
            current_loss = float(raw) if raw else 0.0
        except Exception:
            current_loss = context.daily_pnl_usdt

        passed = abs(current_loss) <= self.max_loss_usdt
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else f"Daily loss {abs(current_loss):.2f} exceeds limit {self.max_loss_usdt:.2f}",
            details={"current_loss": current_loss, "limit": self.max_loss_usdt},
        )


class MaxConsecutiveFailuresRule(RiskRule):
    def __init__(self, max_failures: int, redis_client: RedisClient, **kwargs: Any) -> None:
        super().__init__("max_consecutive_failures", **kwargs)
        self.max_failures = max_failures
        self._redis = redis_client

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        try:
            raw = await self._redis.get("risk:consecutive_failures")
            failures = int(raw) if raw else 0
        except Exception:
            failures = context.consecutive_failures

        passed = failures < self.max_failures
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else f"{failures} consecutive failures >= limit {self.max_failures}",
            details={"consecutive_failures": failures, "limit": self.max_failures},
        )


class MaxSlippageRule(RiskRule):
    def __init__(self, max_slippage_pct: float, **kwargs: Any) -> None:
        super().__init__("max_slippage", **kwargs)
        self.max_slippage_pct = max_slippage_pct

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        slippage = opportunity.estimated_slippage_pct
        passed = slippage <= self.max_slippage_pct
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else f"Slippage {slippage:.4f}% exceeds limit {self.max_slippage_pct:.4f}%",
            details={"slippage_pct": slippage, "limit": self.max_slippage_pct},
        )


class MinProfitRule(RiskRule):
    def __init__(self, min_profit_pct: float, min_profit_usdt: float = 0.0, **kwargs: Any) -> None:
        super().__init__("min_profit", **kwargs)
        self.min_profit_pct = min_profit_pct
        self.min_profit_usdt = min_profit_usdt

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        pct = opportunity.estimated_net_profit_pct
        usdt_profit = opportunity.executable_value_usdt * (pct / 100.0)
        pct_ok = pct >= self.min_profit_pct
        usdt_ok = usdt_profit >= self.min_profit_usdt if self.min_profit_usdt > 0 else True
        passed = pct_ok and usdt_ok
        reasons: list[str] = []
        if not pct_ok:
            reasons.append(f"profit {pct:.4f}% < min {self.min_profit_pct:.4f}%")
        if not usdt_ok:
            reasons.append(f"profit ${usdt_profit:.2f} < min ${self.min_profit_usdt:.2f}")
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="; ".join(reasons),
            details={
                "profit_pct": pct,
                "profit_usdt": usdt_profit,
                "min_pct": self.min_profit_pct,
                "min_usdt": self.min_profit_usdt,
            },
        )


class MinDepthRule(RiskRule):
    def __init__(self, min_depth_usdt: float, **kwargs: Any) -> None:
        super().__init__("min_depth", **kwargs)
        self.min_depth_usdt = min_depth_usdt

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        buy_depth = opportunity.orderbook_depth_buy
        sell_depth = opportunity.orderbook_depth_sell
        min_side = min(buy_depth, sell_depth)
        passed = min_side >= self.min_depth_usdt
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else (
                f"Depth (buy={buy_depth:.2f}, sell={sell_depth:.2f}) "
                f"below min {self.min_depth_usdt:.2f}"
            ),
            details={
                "buy_depth": buy_depth,
                "sell_depth": sell_depth,
                "limit": self.min_depth_usdt,
            },
        )


class DataFreshnessRule(RiskRule):
    def __init__(self, market_data: MarketDataService, max_age_s: float = 5.0, **kwargs: Any) -> None:
        super().__init__("data_freshness", **kwargs)
        self._market_data = market_data
        self.max_age_s = max_age_s

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        stale_pairs: list[str] = []
        for exchange in opportunity.exchanges:
            for symbol in opportunity.symbols:
                age = self._market_data.get_data_age(exchange, symbol)
                if age is None or age > self.max_age_s:
                    stale_pairs.append(f"{exchange}:{symbol} (age={age:.1f}s)" if age else f"{exchange}:{symbol} (no data)")

        passed = len(stale_pairs) == 0
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else f"Stale data: {', '.join(stale_pairs)}",
            details={"stale_pairs": stale_pairs, "max_age_s": self.max_age_s},
        )


class BalanceSufficiencyRule(RiskRule):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__("balance_sufficiency", **kwargs)

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        # For cross-exchange: need quote asset on buy exchange, base asset on sell exchange
        if opportunity.strategy_type == "CROSS_EXCHANGE":
            symbols = opportunity.symbol.split("/") if "/" in opportunity.symbol else []
            if len(symbols) != 2:
                return RiskCheckResult(rule_name=self.name, passed=True, reason="Cannot parse symbol")
            base_asset, quote_asset = symbols

            buy_exchange = opportunity.buy_exchange
            sell_exchange = opportunity.sell_exchange

            # Check quote asset balance on buy exchange
            buy_balance = context.balances.get(buy_exchange, {}).get(quote_asset, 0.0)
            needed_buy = opportunity.executable_value_usdt
            buy_ok = buy_balance >= needed_buy

            # Check base asset balance on sell exchange
            sell_balance = context.balances.get(sell_exchange, {}).get(base_asset, 0.0)
            needed_sell = opportunity.executable_quantity
            sell_ok = sell_balance >= needed_sell

            passed = buy_ok and sell_ok
            reasons: list[str] = []
            if not buy_ok:
                reasons.append(
                    f"Insufficient {quote_asset} on {buy_exchange}: "
                    f"need {needed_buy:.4f}, have {buy_balance:.4f}"
                )
            if not sell_ok:
                reasons.append(
                    f"Insufficient {base_asset} on {sell_exchange}: "
                    f"need {needed_sell:.8f}, have {sell_balance:.8f}"
                )

            return RiskCheckResult(
                rule_name=self.name,
                passed=passed,
                reason="; ".join(reasons),
                details={
                    "buy_exchange": buy_exchange,
                    "sell_exchange": sell_exchange,
                    "buy_balance": buy_balance,
                    "sell_balance": sell_balance,
                    "needed_buy": needed_buy,
                    "needed_sell": needed_sell,
                },
            )

        # For triangular: need starting asset on the exchange
        return RiskCheckResult(rule_name=self.name, passed=True, reason="Triangular balance check skipped")


class MaxExposureRule(RiskRule):
    def __init__(self, max_exposure_usdt: float, **kwargs: Any) -> None:
        super().__init__("max_exposure", **kwargs)
        self.max_exposure_usdt = max_exposure_usdt

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        violations: list[str] = []
        for exchange in opportunity.exchanges:
            current = context.exchange_exposure.get(exchange, 0.0)
            projected = current + opportunity.executable_value_usdt
            if projected > self.max_exposure_usdt:
                violations.append(
                    f"{exchange}: exposure {projected:.2f} > limit {self.max_exposure_usdt:.2f}"
                )
        passed = len(violations) == 0
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="; ".join(violations),
            details={"exchange_exposure": context.exchange_exposure, "limit": self.max_exposure_usdt},
        )


class MaxConcurrentRule(RiskRule):
    def __init__(self, max_concurrent: int, redis_client: RedisClient, **kwargs: Any) -> None:
        super().__init__("max_concurrent", **kwargs)
        self.max_concurrent = max_concurrent
        self._redis = redis_client

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        try:
            raw = await self._redis.get("risk:concurrent_executions")
            concurrent = int(raw) if raw else 0
        except Exception:
            concurrent = context.concurrent_executions

        passed = concurrent < self.max_concurrent
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else f"{concurrent} concurrent executions >= limit {self.max_concurrent}",
            details={"concurrent": concurrent, "limit": self.max_concurrent},
        )


class SymbolWhitelistBlacklistRule(RiskRule):
    """Checks if the opportunity's symbol is on the whitelist (if configured)
    and not on the blacklist."""

    def __init__(
        self,
        whitelist: list[str] | None = None,
        blacklist: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("symbol_whitelist_blacklist", **kwargs)
        self.whitelist = whitelist or []
        self.blacklist = blacklist or []

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        symbol = opportunity.symbol

        if self.blacklist and symbol in self.blacklist:
            return RiskCheckResult(
                rule_name=self.name,
                passed=False,
                reason=f"Symbol {symbol} is blacklisted",
                details={"symbol": symbol, "blacklist": self.blacklist},
            )

        if self.whitelist and symbol not in self.whitelist:
            return RiskCheckResult(
                rule_name=self.name,
                passed=False,
                reason=f"Symbol {symbol} is not in the whitelist",
                details={"symbol": symbol, "whitelist": self.whitelist},
            )

        return RiskCheckResult(
            rule_name=self.name,
            passed=True,
            reason="",
            details={"symbol": symbol},
        )


class MinOrderbookDepthRule(RiskRule):
    """Checks that the orderbook depth on both sides meets a minimum USDT threshold.

    Uses ``orderbook_depth_buy`` and ``orderbook_depth_sell`` from
    :class:`OpportunityCandidate`.  If both values are zero (i.e. depth info
    is not populated) the check passes automatically.
    """

    def __init__(self, min_depth_usdt: float, **kwargs: Any) -> None:
        super().__init__("min_orderbook_depth", **kwargs)
        self.min_depth_usdt = min_depth_usdt

    async def check(self, opportunity: OpportunityCandidate, context: RiskContext) -> RiskCheckResult:
        buy_depth = opportunity.orderbook_depth_buy
        sell_depth = opportunity.orderbook_depth_sell

        # If the opportunity doesn't carry depth info, pass the check
        if buy_depth == 0.0 and sell_depth == 0.0:
            return RiskCheckResult(
                rule_name=self.name,
                passed=True,
                reason="No orderbook depth info available, skipping check",
            )

        min_side = min(buy_depth, sell_depth)
        passed = min_side >= self.min_depth_usdt
        return RiskCheckResult(
            rule_name=self.name,
            passed=passed,
            reason="" if passed else (
                f"Orderbook depth (buy={buy_depth:.2f}, sell={sell_depth:.2f}) "
                f"below min {self.min_depth_usdt:.2f}"
            ),
            details={
                "buy_depth": buy_depth,
                "sell_depth": sell_depth,
                "limit": self.min_depth_usdt,
            },
        )


# ---------------------------------------------------------------------------
# RiskEngine
# ---------------------------------------------------------------------------

class RiskEngine:
    """Evaluates opportunities against all enabled risk rules.

    Dependencies are injected at construction time. The engine is stateless
    aside from the rule list and the DB session factory for persistence.
    """

    def __init__(
        self,
        event_bus: EventBus,
        redis_client: RedisClient,
        session_factory: async_sessionmaker[AsyncSession],
        market_data: MarketDataService,
        config: Settings | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._redis = redis_client
        self._session_factory = session_factory
        self._market_data = market_data
        self._cfg = config or settings

        # Build the rule chain
        self._rules: list[RiskRule] = self._build_default_rules()

    def _build_default_rules(self) -> list[RiskRule]:
        cfg = self._cfg.risk
        return [
            MaxOrderValueRule(max_value_usdt=cfg.max_order_value_usdt),
            MaxDailyLossRule(max_loss_usdt=cfg.max_daily_loss_usdt, redis_client=self._redis),
            MaxConsecutiveFailuresRule(max_failures=cfg.max_consecutive_failures, redis_client=self._redis),
            MaxSlippageRule(max_slippage_pct=cfg.max_slippage_pct),
            MinProfitRule(
                min_profit_pct=cfg.min_profit_threshold_pct,
                min_profit_usdt=cfg.min_profit_threshold_usdt,
            ),
            MinDepthRule(min_depth_usdt=self._cfg.strategy.min_depth_usdt),
            DataFreshnessRule(market_data=self._market_data, max_age_s=5.0),
            BalanceSufficiencyRule(),
            MaxExposureRule(max_exposure_usdt=cfg.max_position_value_usdt),
            MaxConcurrentRule(max_concurrent=cfg.max_open_orders, redis_client=self._redis),
            SymbolWhitelistBlacklistRule(
                whitelist=list(self._cfg.strategy.enabled_pairs),
                blacklist=[],
            ),
            MinOrderbookDepthRule(min_depth_usdt=self._cfg.strategy.min_depth_usdt),
        ]

    @property
    def rules(self) -> list[RiskRule]:
        return list(self._rules)

    def add_rule(self, rule: RiskRule) -> None:
        self._rules.append(rule)
        logger.info("Risk rule added: {}", rule.name)

    def remove_rule(self, name: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        removed = len(self._rules) < before
        if removed:
            logger.info("Risk rule removed: {}", name)
        return removed

    def enable_rule(self, name: str) -> bool:
        for rule in self._rules:
            if rule.name == name:
                rule.enabled = True
                return True
        return False

    def disable_rule(self, name: str) -> bool:
        for rule in self._rules:
            if rule.name == name:
                rule.enabled = False
                return True
        return False

    async def evaluate(
        self,
        opportunity: OpportunityCandidate,
        context: RiskContext | None = None,
    ) -> RiskDecision:
        """Run all enabled risk rules against the opportunity.

        Returns a :class:`RiskDecision` that is approved only if every
        enabled rule passes.
        """
        if context is None:
            context = RiskContext()

        results: list[RiskCheckResult] = []

        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                result = await rule.check(opportunity, context)
                results.append(result)
            except Exception as exc:
                logger.opt(exception=True).error("Risk rule {} raised", rule.name)
                results.append(RiskCheckResult(
                    rule_name=rule.name,
                    passed=False,
                    reason=f"Rule raised exception: {exc}",
                ))

        decision = RiskDecision(
            approved=all(r.passed for r in results),
            results=results,
        )

        # Log and persist violations
        if not decision.approved:
            logger.warning(
                "Risk BLOCKED opportunity {}: violations={}",
                opportunity.id,
                decision.violation_names,
            )
            await self._persist_violations(opportunity, decision)
            await self._event_bus.publish(
                EventType.RISK_VIOLATION,
                {
                    "opportunity_id": opportunity.id,
                    "violations": [
                        {"rule": r.rule_name, "reason": r.reason, "details": r.details}
                        for r in decision.violations
                    ],
                },
            )
        else:
            logger.info("Risk APPROVED opportunity {}", opportunity.id)

        return decision

    async def _persist_violations(
        self,
        opportunity: OpportunityCandidate,
        decision: RiskDecision,
    ) -> None:
        """Store risk violations in the database."""
        try:
            async with self._session_factory() as session:
                for violation in decision.violations:
                    event = RiskEvent(
                        rule_name=violation.rule_name,
                        rule_category="pre_trade",
                        severity=RiskSeverity.WARNING,
                        event_type=RiskEventType.BLOCKED,
                        details_json=violation.details,
                        threshold_value=violation.details.get("limit"),
                        actual_value=violation.details.get(
                            "order_value",
                            violation.details.get("slippage_pct"),
                        ),
                        message=violation.reason,
                    )
                    session.add(event)
                await session.commit()
        except Exception:
            logger.opt(exception=True).error("Failed to persist risk violations")

    # ------------------------------------------------------------------
    # In-trade and post-trade checks
    # ------------------------------------------------------------------

    async def check_in_trade(self, execution_id: str, elapsed_ms: float, partial_fills: int) -> RiskCheckResult:
        """In-trade risk check - verify execution isn't taking too long or stuck."""
        max_execution_time_ms = self._cfg.strategy.execution_timeout_s * 1000
        if elapsed_ms > max_execution_time_ms:
            return RiskCheckResult(
                rule_name="execution_timeout",
                passed=False,
                reason=f"Execution exceeded timeout: {elapsed_ms:.0f}ms > {max_execution_time_ms:.0f}ms",
            )
        return RiskCheckResult(rule_name="execution_timeout", passed=True, reason="Within time limit")

    async def check_post_trade(self, execution_id: str, planned_profit_pct: float, actual_profit_pct: float) -> RiskCheckResult:
        """Post-trade risk check - verify actual vs planned deviation."""
        deviation = abs(actual_profit_pct - planned_profit_pct)
        if deviation > 0.5:  # 0.5% deviation threshold
            return RiskCheckResult(
                rule_name="profit_deviation",
                passed=False,
                reason=f"Actual profit deviated {deviation:.2f}% from planned",
                details={"planned": planned_profit_pct, "actual": actual_profit_pct, "deviation": deviation},
            )
        return RiskCheckResult(rule_name="profit_deviation", passed=True, reason="Profit within expected range")

    # ------------------------------------------------------------------
    # Redis helpers for external updates (called by execution engine)
    # ------------------------------------------------------------------

    async def record_daily_pnl(self, pnl_usdt: float) -> None:
        """Atomically update today's cumulative PnL in Redis."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"risk:daily_loss:{today}"
        try:
            current_raw = await self._redis.get(key)
            current = float(current_raw) if current_raw else 0.0
            new_val = current + pnl_usdt
            await self._redis.set(key, str(new_val), ttl_s=86400)
        except Exception:
            logger.opt(exception=True).error("Failed to record daily PnL")

    async def record_execution_result(self, success: bool) -> None:
        """Update consecutive failure counter in Redis."""
        key = "risk:consecutive_failures"
        try:
            if success:
                await self._redis.set(key, "0")
            else:
                await self._redis.incr(key)
                await self._redis.expire(key, 86400)
        except Exception:
            logger.opt(exception=True).error("Failed to update consecutive failures")

    async def increment_concurrent(self) -> None:
        try:
            await self._redis.incr("risk:concurrent_executions")
        except Exception:
            logger.opt(exception=True).error("Failed to increment concurrent count")

    async def decrement_concurrent(self) -> None:
        try:
            raw = await self._redis.get("risk:concurrent_executions")
            current = int(raw) if raw else 0
            new_val = max(0, current - 1)
            await self._redis.set("risk:concurrent_executions", str(new_val))
        except Exception:
            logger.opt(exception=True).error("Failed to decrement concurrent count")
