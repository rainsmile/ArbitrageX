"""
AlertService -- configurable alert rules with persistence, event bus
integration, and notification channel support (log, Telegram, email).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import httpx
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.db.redis import RedisClient
from app.models.alert import Alert, AlertSeverity
from app.services.market_data import MarketDataService
from app.exchanges.factory import ExchangeFactory


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AlertCandidate:
    """In-memory representation before DB persistence."""
    alert_type: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    title: str
    message: str
    source: str = "alert_service"
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class AlertRule:
    """A condition that can trigger an alert."""
    name: str
    enabled: bool = True
    severity: str = "WARNING"
    message_template: str = ""
    check_fn: Callable[..., Coroutine[Any, Any, AlertCandidate | None]] | None = None
    cooldown_s: float = 300.0  # Minimum seconds between repeated alerts
    last_triggered: float = 0.0

    def can_trigger(self) -> bool:
        if not self.enabled:
            return False
        return (time.time() - self.last_triggered) >= self.cooldown_s


# ---------------------------------------------------------------------------
# AlertService
# ---------------------------------------------------------------------------

class AlertService:
    """Manages alert rules, checks conditions, persists alerts, and dispatches
    notifications through configured channels.
    """

    def __init__(
        self,
        event_bus: EventBus,
        redis_client: RedisClient,
        session_factory: async_sessionmaker[AsyncSession],
        market_data: MarketDataService,
        exchange_factory: ExchangeFactory,
        config: Settings | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._redis = redis_client
        self._session_factory = session_factory
        self._market_data = market_data
        self._exchange_factory = exchange_factory
        self._cfg = config or settings

        self._rules: list[AlertRule] = []
        self._running = False
        self._check_interval_s: float = 30.0
        self._task: asyncio.Task[None] | None = None

        # Register built-in alert rules
        self._register_builtin_rules()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop(), name="alert-check-loop")
        logger.info("AlertService started ({} rules)", len(self._rules))

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("AlertService stopped")

    async def _check_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._check_interval_s)
                await self.check_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("Alert check loop error")

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def register_alert_rule(
        self,
        name: str,
        check_fn: Callable[..., Coroutine[Any, Any, AlertCandidate | None]],
        severity: str = "WARNING",
        message_template: str = "",
        cooldown_s: float = 300.0,
    ) -> None:
        """Register a custom alert rule."""
        rule = AlertRule(
            name=name,
            severity=severity,
            message_template=message_template,
            check_fn=check_fn,
            cooldown_s=cooldown_s,
        )
        self._rules.append(rule)
        logger.info("Alert rule registered: {}", name)

    def _register_builtin_rules(self) -> None:
        """Register all built-in alert checks."""
        self._rules = [
            AlertRule(
                name="exchange_disconnected",
                severity="CRITICAL",
                message_template="Exchange {exchange} appears disconnected",
                check_fn=self._check_exchange_disconnected,
                cooldown_s=120.0,
            ),
            AlertRule(
                name="data_stale",
                severity="WARNING",
                message_template="Market data stale for {count} pairs",
                check_fn=self._check_data_stale,
                cooldown_s=60.0,
            ),
            AlertRule(
                name="consecutive_failures",
                severity="CRITICAL",
                message_template="Consecutive execution failures: {count}",
                check_fn=self._check_consecutive_failures,
                cooldown_s=300.0,
            ),
            AlertRule(
                name="daily_loss_exceeded",
                severity="CRITICAL",
                message_template="Daily loss limit approached: ${loss:.2f}",
                check_fn=self._check_daily_loss,
                cooldown_s=600.0,
            ),
            AlertRule(
                name="low_balance",
                severity="WARNING",
                message_template="Low balance detected on {exchange}: {asset}",
                check_fn=self._check_low_balance,
                cooldown_s=600.0,
            ),
            AlertRule(
                name="high_exposure",
                severity="WARNING",
                message_template="High exchange exposure: {exchange} at {pct:.1f}%",
                check_fn=self._check_high_exposure,
                cooldown_s=600.0,
            ),
        ]

    # ------------------------------------------------------------------
    # Built-in check implementations
    # ------------------------------------------------------------------

    async def _check_exchange_disconnected(self) -> AlertCandidate | None:
        """Check if any exchange has no recent data updates."""
        adapters = self._exchange_factory.get_all()
        disconnected: list[str] = []

        for name in adapters:
            # Check if we have any recent ticker from this exchange
            has_recent = False
            all_tickers = self._market_data.get_all_tickers()
            for (exch, _), _ in all_tickers.items():
                if exch == name:
                    # Check if data is not stale (use a generous threshold)
                    for symbol in self._cfg.strategy.enabled_pairs[:1]:
                        age = self._market_data.get_data_age(name, symbol)
                        if age is not None and age < 30.0:
                            has_recent = True
                            break
                if has_recent:
                    break

            if not has_recent and all_tickers:
                disconnected.append(name)

        if disconnected:
            return AlertCandidate(
                alert_type="EXCHANGE_DISCONNECTED",
                severity="CRITICAL",
                title=f"Exchange disconnected: {', '.join(disconnected)}",
                message=f"No recent market data from: {', '.join(disconnected)}. WebSocket may be down.",
                details={"exchanges": disconnected},
            )
        return None

    async def _check_data_stale(self) -> AlertCandidate | None:
        """Check for stale market data."""
        stale_count = 0
        stale_pairs: list[str] = []

        adapters = self._exchange_factory.get_all()
        for name in adapters:
            for symbol in self._cfg.strategy.enabled_pairs:
                if self._market_data.is_data_stale(name, symbol):
                    stale_count += 1
                    if len(stale_pairs) < 5:
                        stale_pairs.append(f"{name}:{symbol}")

        # Alert if more than 25% of data points are stale
        total_expected = len(adapters) * len(self._cfg.strategy.enabled_pairs)
        if total_expected > 0 and stale_count / total_expected > 0.25:
            return AlertCandidate(
                alert_type="DATA_STALE",
                severity="WARNING",
                title=f"Stale market data: {stale_count} pairs",
                message=f"{stale_count}/{total_expected} data points are stale. Examples: {', '.join(stale_pairs)}",
                details={"stale_count": stale_count, "total": total_expected, "examples": stale_pairs},
            )
        return None

    async def _check_consecutive_failures(self) -> AlertCandidate | None:
        """Check consecutive execution failure count."""
        try:
            raw = await self._redis.get("risk:consecutive_failures")
            failures = int(raw) if raw else 0
        except Exception:
            return None

        threshold = self._cfg.risk.max_consecutive_failures
        if failures >= threshold:
            return AlertCandidate(
                alert_type="CONSECUTIVE_FAILURES",
                severity="CRITICAL",
                title=f"Consecutive failures: {failures}",
                message=f"{failures} consecutive execution failures (threshold: {threshold}). Trading may be paused.",
                details={"failures": failures, "threshold": threshold},
            )
        return None

    async def _check_daily_loss(self) -> AlertCandidate | None:
        """Check if daily loss is approaching the limit."""
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            raw = await self._redis.get(f"risk:daily_loss:{today}")
            current_loss = float(raw) if raw else 0.0
        except Exception:
            return None

        limit = self._cfg.risk.max_daily_loss_usdt
        # Alert at 80% of limit
        if abs(current_loss) >= limit * 0.8:
            return AlertCandidate(
                alert_type="DAILY_LOSS_WARNING",
                severity="CRITICAL",
                title=f"Daily loss approaching limit: ${abs(current_loss):.2f}",
                message=f"Current daily loss: ${abs(current_loss):.2f} (limit: ${limit:.2f}, {abs(current_loss)/limit*100:.0f}%)",
                details={"current_loss": current_loss, "limit": limit},
            )
        return None

    async def _check_low_balance(self) -> AlertCandidate | None:
        """Check for low USDT/stablecoin balances on any exchange."""
        low_exchanges: list[dict[str, Any]] = []
        min_balance_usdt = 100.0  # Alert if USDT balance below this

        adapters = self._exchange_factory.get_all()
        for name in adapters:
            try:
                # Check Redis cache for balance
                raw = await self._redis.get_json(f"balance:{name}:USDT")
                if raw:
                    free = float(raw.get("free", 0))
                    if free < min_balance_usdt:
                        low_exchanges.append({"exchange": name, "asset": "USDT", "free": free})
            except Exception:
                continue

        if low_exchanges:
            first = low_exchanges[0]
            parts = [
                "{exch}:{asset}=${free:.2f}".format(
                    exch=e["exchange"], asset=e["asset"], free=e["free"],
                )
                for e in low_exchanges
            ]
            return AlertCandidate(
                alert_type="LOW_BALANCE",
                severity="WARNING",
                title=f"Low balance on {first['exchange']}: {first['asset']} = ${first['free']:.2f}",
                message=f"Low balances detected: {', '.join(parts)}",
                details={"low_balances": low_exchanges},
            )
        return None

    async def _check_high_exposure(self) -> AlertCandidate | None:
        """Check if too much value is concentrated on one exchange."""
        adapters = self._exchange_factory.get_all()
        if len(adapters) < 2:
            return None

        exchange_values: dict[str, float] = {}
        for name in adapters:
            total_value = 0.0
            for asset in ["USDT", "BTC", "ETH"]:
                try:
                    raw = await self._redis.get_json(f"balance:{name}:{asset}")
                    if raw:
                        total_value += float(raw.get("usd_value", 0))
                except Exception:
                    continue
            exchange_values[name] = total_value

        grand_total = sum(exchange_values.values())
        if grand_total <= 0:
            return None

        # Alert if any exchange holds more than 70% of total value
        for name, value in exchange_values.items():
            pct = value / grand_total * 100.0
            if pct > 70.0:
                return AlertCandidate(
                    alert_type="HIGH_EXPOSURE",
                    severity="WARNING",
                    title=f"High exposure on {name}: {pct:.1f}%",
                    message=f"Exchange {name} holds {pct:.1f}% of total portfolio (${value:.2f}/${grand_total:.2f})",
                    details={"exchange": name, "pct": pct, "value": value, "total": grand_total},
                )
        return None

    # ------------------------------------------------------------------
    # Check + send
    # ------------------------------------------------------------------

    async def check_all(self) -> list[AlertCandidate]:
        """Run all enabled alert rules and send alerts for triggered ones."""
        triggered: list[AlertCandidate] = []

        for rule in self._rules:
            if not rule.can_trigger() or rule.check_fn is None:
                continue
            try:
                candidate = await rule.check_fn()
                if candidate is not None:
                    rule.last_triggered = time.time()
                    triggered.append(candidate)
                    await self.send_alert(candidate)
            except Exception:
                logger.opt(exception=True).error("Alert rule {} check failed", rule.name)

        if triggered:
            logger.info("Alert check triggered {} alerts", len(triggered))

        return triggered

    async def send_alert(self, alert: AlertCandidate) -> None:
        """Persist alert to DB, publish to event bus, and send to configured channels."""
        # Persist to DB
        db_alert = await self._persist_alert(alert)

        # Publish event
        await self._event_bus.publish(
            EventType.ALERT_TRIGGERED,
            {
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "title": alert.title,
                "message": alert.message,
                "details": alert.details,
            },
        )

        # Send to configured channels
        channels = self._cfg.alert.enabled_channels
        for channel in channels:
            try:
                if channel == "log":
                    await self._send_log(alert)
                elif channel == "telegram":
                    await self._send_telegram(alert)
                elif channel == "email":
                    await self._send_email(alert)
            except Exception:
                logger.opt(exception=True).error(
                    "Failed to send alert via {}", channel,
                )

    async def _persist_alert(self, alert: AlertCandidate) -> Alert | None:
        """Save alert to the database."""
        try:
            severity_map = {
                "INFO": AlertSeverity.INFO,
                "WARNING": AlertSeverity.WARNING,
                "CRITICAL": AlertSeverity.CRITICAL,
            }

            async with self._session_factory() as session:
                db_alert = Alert(
                    alert_type=alert.alert_type,
                    severity=severity_map.get(alert.severity, AlertSeverity.WARNING),
                    title=alert.title,
                    message=alert.message,
                    source=alert.source,
                    details_json=alert.details,
                )
                session.add(db_alert)
                await session.commit()
                await session.refresh(db_alert)
                return db_alert
        except Exception:
            logger.opt(exception=True).error("Failed to persist alert to DB")
            return None

    # ------------------------------------------------------------------
    # Alert resolution
    # ------------------------------------------------------------------

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "system") -> bool:
        """Mark alert as acknowledged (read) without resolving. Returns True if found."""
        try:
            async with self._session_factory() as session:
                import uuid as _uuid
                stmt = (
                    update(Alert)
                    .where(Alert.id == _uuid.UUID(alert_id))
                    .values(is_read=True)
                )
                result = await session.execute(stmt)
                await session.commit()
                found = (result.rowcount or 0) > 0

                if found:
                    # Log audit entry if audit_service is available
                    try:
                        from app.services.audit import AuditService
                        # We don't have a direct reference to audit_service here,
                        # so we log via loguru as a fallback audit trail.
                        logger.info(
                            "Alert {} acknowledged by {}",
                            alert_id, acknowledged_by,
                        )
                    except Exception:
                        pass

                return found
        except Exception:
            logger.opt(exception=True).error(
                "Failed to acknowledge alert {}", alert_id,
            )
            return False

    async def mark_resolved(self, alert_id: str) -> bool:
        """Mark an alert as resolved by its UUID string."""
        try:
            async with self._session_factory() as session:
                import uuid as _uuid
                stmt = (
                    update(Alert)
                    .where(Alert.id == _uuid.UUID(alert_id))
                    .values(
                        is_resolved=True,
                        resolved_at=datetime.now(timezone.utc),
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return (result.rowcount or 0) > 0
        except Exception:
            logger.opt(exception=True).error("Failed to mark alert {} resolved", alert_id)
            return False

    async def get_active_alerts(self, limit: int = 50) -> list[Alert]:
        """Return unresolved alerts ordered by severity and creation time."""
        try:
            async with self._session_factory() as session:
                stmt = (
                    select(Alert)
                    .where(Alert.is_resolved == False)  # noqa: E712
                    .order_by(Alert.severity.desc(), Alert.created_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except Exception:
            logger.opt(exception=True).error("Failed to fetch active alerts")
            return []

    # ------------------------------------------------------------------
    # Notification channels
    # ------------------------------------------------------------------

    async def _send_log(self, alert: AlertCandidate) -> None:
        """Log the alert using loguru."""
        level = "WARNING" if alert.severity in ("WARNING", "CRITICAL") else "INFO"
        logger.log(
            level,
            "[ALERT] [{sev}] {title}: {msg}",
            sev=alert.severity,
            title=alert.title,
            msg=alert.message,
        )

    async def _send_telegram(self, alert: AlertCandidate) -> None:
        """Send alert via Telegram Bot API.

        Requires ``ALERT_TELEGRAM_BOT_TOKEN`` and ``ALERT_TELEGRAM_CHAT_ID``
        environment variables to be set.
        """
        bot_token = self._cfg.alert.telegram_bot_token
        chat_id = self._cfg.alert.telegram_chat_id

        if not bot_token or not chat_id:
            logger.debug("Telegram alert skipped: bot_token or chat_id not configured")
            return

        severity_emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨"}
        emoji = severity_emoji.get(alert.severity, "📢")

        text = (
            f"{emoji} *{alert.severity}*\n"
            f"*{alert.title}*\n\n"
            f"{alert.message}"
        )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "Telegram API returned {}: {}",
                        response.status_code, response.text,
                    )
                else:
                    logger.debug("Telegram alert sent: {}", alert.title)
        except Exception:
            logger.opt(exception=True).warning("Failed to send Telegram alert")

    async def _send_email(self, alert: AlertCandidate) -> None:
        """Send alert via SMTP email.

        Requires ``ALERT_EMAIL_*`` environment variables to be set.
        Uses aiosmtplib if available, otherwise logs a placeholder message.
        """
        smtp_host = self._cfg.alert.email_smtp_host
        email_from = self._cfg.alert.email_from
        email_to = self._cfg.alert.email_to
        email_password = self._cfg.alert.email_password
        smtp_port = self._cfg.alert.email_smtp_port

        if not smtp_host or not email_from or not email_to:
            logger.debug("Email alert skipped: SMTP not configured")
            return

        subject = f"[{alert.severity}] {alert.title}"
        body = (
            f"Severity: {alert.severity}\n"
            f"Type: {alert.alert_type}\n"
            f"Title: {alert.title}\n\n"
            f"{alert.message}\n\n"
            f"Details: {alert.details}"
        )

        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = email_from
            msg["To"] = email_to

            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=email_from,
                password=email_password,
                start_tls=True,
            )
            logger.debug("Email alert sent: {}", subject)
        except ImportError:
            logger.warning(
                "aiosmtplib not installed; email alert not sent. "
                "Install with: pip install aiosmtplib"
            )
        except Exception:
            logger.opt(exception=True).warning("Failed to send email alert")
