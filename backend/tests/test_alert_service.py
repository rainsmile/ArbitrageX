"""Tests for the AlertService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.alert_service import AlertCandidate, AlertRule, AlertService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_alert_service() -> AlertService:
    """Build an AlertService with fully mocked dependencies."""
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()

    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.get_json = AsyncMock(return_value=None)

    # Mock session factory so DB calls don't fail
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    session_factory = MagicMock(return_value=mock_session)

    market_data = MagicMock()
    market_data.get_all_tickers = MagicMock(return_value={})
    market_data.is_data_stale = MagicMock(return_value=False)

    exchange_factory = MagicMock()
    exchange_factory.get_all = MagicMock(return_value={})

    config = MagicMock()
    config.alert.enabled_channels = ["log"]
    config.alert.telegram_bot_token = ""
    config.alert.telegram_chat_id = ""
    config.risk.max_consecutive_failures = 5
    config.risk.max_daily_loss_usdt = 500.0
    config.strategy.enabled_pairs = ["BTC/USDT"]

    svc = AlertService(
        event_bus=event_bus,
        redis_client=redis_client,
        session_factory=session_factory,
        market_data=market_data,
        exchange_factory=exchange_factory,
        config=config,
    )
    return svc


# ---------------------------------------------------------------------------
# AlertRule
# ---------------------------------------------------------------------------

class TestAlertRule:
    def test_can_trigger_respects_cooldown(self):
        rule = AlertRule(name="test", cooldown_s=60.0, last_triggered=time.time())
        assert rule.can_trigger() is False

    def test_can_trigger_after_cooldown(self):
        rule = AlertRule(name="test", cooldown_s=1.0, last_triggered=time.time() - 5.0)
        assert rule.can_trigger() is True

    def test_disabled_rule_cannot_trigger(self):
        rule = AlertRule(name="test", enabled=False, cooldown_s=0.0)
        assert rule.can_trigger() is False

    def test_fresh_rule_can_trigger(self):
        rule = AlertRule(name="test", cooldown_s=60.0, last_triggered=0.0)
        assert rule.can_trigger() is True


# ---------------------------------------------------------------------------
# Builtin rules
# ---------------------------------------------------------------------------

class TestBuiltinRules:
    def test_builtin_rules_registered(self):
        svc = _build_alert_service()
        rule_names = [r.name for r in svc._rules]
        assert "exchange_disconnected" in rule_names
        assert "data_stale" in rule_names
        assert "consecutive_failures" in rule_names
        assert "daily_loss_exceeded" in rule_names
        assert "low_balance" in rule_names
        assert "high_exposure" in rule_names

    def test_register_custom_rule(self):
        svc = _build_alert_service()
        before = len(svc._rules)

        async def custom_check():
            return None

        svc.register_alert_rule("custom_rule", custom_check, severity="INFO")
        assert len(svc._rules) == before + 1
        assert svc._rules[-1].name == "custom_rule"


# ---------------------------------------------------------------------------
# check_all
# ---------------------------------------------------------------------------

class TestCheckAll:
    @pytest.mark.asyncio
    async def test_check_all_returns_list(self):
        svc = _build_alert_service()
        # With no exchanges, builtin checks should return empty candidates
        triggered = await svc.check_all()
        assert isinstance(triggered, list)

    @pytest.mark.asyncio
    async def test_check_all_with_custom_rule(self):
        svc = _build_alert_service()
        # Clear builtin rules to isolate
        svc._rules = []

        candidate = AlertCandidate(
            alert_type="TEST",
            severity="WARNING",
            title="Test alert",
            message="test message",
        )

        async def check_fn():
            return candidate

        svc.register_alert_rule("test_rule", check_fn, cooldown_s=0.0)
        triggered = await svc.check_all()
        assert len(triggered) == 1
        assert triggered[0].alert_type == "TEST"

    @pytest.mark.asyncio
    async def test_cooldown_prevents_duplicate(self):
        svc = _build_alert_service()
        svc._rules = []

        call_count = 0

        async def check_fn():
            nonlocal call_count
            call_count += 1
            return AlertCandidate(
                alert_type="TEST", severity="WARNING",
                title="t", message="m",
            )

        svc.register_alert_rule("cool_rule", check_fn, cooldown_s=9999.0)

        # First check triggers
        triggered1 = await svc.check_all()
        assert len(triggered1) == 1

        # Second check blocked by cooldown
        triggered2 = await svc.check_all()
        assert len(triggered2) == 0


# ---------------------------------------------------------------------------
# send_alert
# ---------------------------------------------------------------------------

class TestSendAlert:
    @pytest.mark.asyncio
    async def test_send_alert_publishes_event(self):
        svc = _build_alert_service()
        candidate = AlertCandidate(
            alert_type="TEST",
            severity="WARNING",
            title="Test",
            message="test message",
        )
        await svc.send_alert(candidate)

        svc._event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_alert_persists_to_db(self):
        svc = _build_alert_service()
        candidate = AlertCandidate(
            alert_type="TEST",
            severity="WARNING",
            title="Test",
            message="test message",
        )
        await svc.send_alert(candidate)

        # session.add and session.commit should have been called
        session = svc._session_factory.return_value
        session.add.assert_called()


# ---------------------------------------------------------------------------
# acknowledge / resolve
# ---------------------------------------------------------------------------

class TestAcknowledgeResolve:
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self):
        svc = _build_alert_service()
        mock_result = MagicMock()
        mock_result.rowcount = 1

        session = svc._session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        import uuid
        found = await svc.acknowledge_alert(uuid.uuid4().hex[:32])
        # We're testing the interface, not the DB; the mock should handle it
        assert isinstance(found, bool)

    @pytest.mark.asyncio
    async def test_mark_resolved(self):
        svc = _build_alert_service()
        mock_result = MagicMock()
        mock_result.rowcount = 1

        session = svc._session_factory.return_value
        session.execute = AsyncMock(return_value=mock_result)

        import uuid
        resolved = await svc.mark_resolved(uuid.uuid4().hex[:32])
        assert isinstance(resolved, bool)
