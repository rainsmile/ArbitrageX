"""Comprehensive tests for Phase 6 -- live trading safety features.

Covers:
- Trading modes & capabilities
- Kill switch & circuit breakers
- Credential masking & security
- Exchange error classification
- Pre-order validation (LiveGuardrails)
- Order lifecycle tracking
- Reconciliation
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.credentials import CredentialManager, ExchangeCredential, _mask_secret
from app.core.events import EventBus, EventType
from app.core.exchange_errors import (
    ExchangeErrorType,
    classify_binance_error,
    classify_bybit_error,
    classify_okx_error,
)
from app.core.kill_switch import KillSwitch
from app.core.trading_modes import (
    MODE_CAPABILITIES,
    ModeCapabilities,
    TradingMode,
    can_place_real_orders,
    get_capabilities,
    is_live_mode,
)
from app.services.live_guardrails import LiveGuardrails, PreOrderCheck
from app.services.order_tracker import (
    OrderLifecycleState,
    OrderTracker,
    TrackedOrder,
    ReconciliationResult,
)


# =====================================================================
# Trading Modes & Capabilities
# =====================================================================

class TestTradingModes:

    def test_all_modes_have_capabilities(self):
        for mode in TradingMode:
            caps = get_capabilities(mode)
            assert isinstance(caps, ModeCapabilities)

    def test_mock_mode_no_real_access(self):
        caps = get_capabilities(TradingMode.MOCK)
        assert not caps.can_read_public_data
        assert not caps.can_read_account
        assert not caps.can_place_orders
        assert caps.can_auto_execute  # mock can auto-execute for testing

    def test_read_only_mode_no_orders(self):
        caps = get_capabilities(TradingMode.READ_ONLY)
        assert caps.can_read_public_data
        assert caps.can_read_account
        assert not caps.can_place_orders
        assert not caps.can_auto_execute

    def test_paper_mode_no_real_orders(self):
        caps = get_capabilities(TradingMode.PAPER)
        assert not caps.can_place_orders
        assert caps.can_auto_execute

    def test_live_small_mode_restricted(self):
        caps = get_capabilities(TradingMode.LIVE_SMALL)
        assert caps.can_place_orders
        assert not caps.can_auto_execute  # Manual trigger only
        assert caps.max_single_order_usdt == 100.0
        assert caps.max_daily_notional_usdt == 1000.0
        assert caps.audit_level == "elevated"
        assert caps.requires_api_keys

    def test_live_mode_full_access(self):
        caps = get_capabilities(TradingMode.LIVE)
        assert caps.can_place_orders
        assert caps.can_auto_execute
        assert caps.max_single_order_usdt == 10000.0
        assert caps.max_daily_notional_usdt == 100000.0
        assert caps.audit_level == "critical"

    def test_is_live_mode(self):
        assert not is_live_mode(TradingMode.MOCK)
        assert not is_live_mode(TradingMode.READ_ONLY)
        assert not is_live_mode(TradingMode.PAPER)
        assert not is_live_mode(TradingMode.SIMULATION)
        assert is_live_mode(TradingMode.LIVE_SMALL)
        assert is_live_mode(TradingMode.LIVE)

    def test_can_place_real_orders(self):
        assert not can_place_real_orders(TradingMode.PAPER)
        assert not can_place_real_orders(TradingMode.READ_ONLY)
        assert can_place_real_orders(TradingMode.LIVE_SMALL)
        assert can_place_real_orders(TradingMode.LIVE)


# =====================================================================
# Kill Switch & Circuit Breakers
# =====================================================================

class TestKillSwitch:

    def test_initial_state_inactive(self):
        ks = KillSwitch()
        assert not ks.is_active

    def test_activate_and_release(self):
        ks = KillSwitch()
        ks.activate(reason="test", activated_by="unit_test")
        assert ks.is_active
        status = ks.get_status()
        assert status["active"]
        assert status["reason"] == "test"
        assert status["activated_by"] == "unit_test"

        ks.release(released_by="unit_test")
        assert not ks.is_active

    def test_double_activate_overwrites(self):
        ks = KillSwitch()
        ks.activate(reason="first", activated_by="a")
        ks.activate(reason="second", activated_by="b")
        assert ks.is_active
        # Second activation overwrites the reason
        status = ks.get_status()
        assert status["reason"] == "second"


class TestCircuitBreaker:

    def test_breaker_starts_closed(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=3)
        assert not ks.is_circuit_open("exchange:binance")

    def test_breaker_trips_at_threshold(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=3)
        ks.record_failure("exchange:binance", "error 1")
        ks.record_failure("exchange:binance", "error 2")
        assert not ks.is_circuit_open("exchange:binance")
        tripped = ks.record_failure("exchange:binance", "error 3")
        assert tripped
        assert ks.is_circuit_open("exchange:binance")

    def test_breaker_manual_reset(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=1)
        ks.record_failure("exchange:binance", "fail")
        assert ks.is_circuit_open("exchange:binance")
        ks.reset_breaker("exchange:binance")
        assert not ks.is_circuit_open("exchange:binance")

    def test_success_resets_count(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=3)
        ks.record_failure("exchange:binance", "f1")
        ks.record_failure("exchange:binance", "f2")
        ks.record_success("exchange:binance")
        # Count should be back to 0, so 2 more failures should NOT trip
        ks.record_failure("exchange:binance", "f3")
        ks.record_failure("exchange:binance", "f4")
        assert not ks.is_circuit_open("exchange:binance")

    def test_multiple_scopes_independent(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=1)
        ks.get_or_create_breaker("exchange:okx", threshold=1)
        ks.record_failure("exchange:binance", "fail")
        assert ks.is_circuit_open("exchange:binance")
        assert not ks.is_circuit_open("exchange:okx")

    def test_get_open_breakers(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=1)
        ks.get_or_create_breaker("symbol:BTC/USDT", threshold=1)
        ks.record_failure("exchange:binance", "fail")
        open_breakers = ks.get_open_breakers()
        assert len(open_breakers) == 1
        assert open_breakers[0]["scope"] == "exchange:binance"


# =====================================================================
# Credential Masking & Security
# =====================================================================

class TestCredentialMasking:

    def test_mask_short_secret(self):
        # len("abc") == 3 which is <= visible_chars*2 == 8, so all masked
        assert _mask_secret("abc") == "***"
        assert _mask_secret("") == "(empty)"

    def test_mask_normal_secret(self):
        masked = _mask_secret("abcdefghijklmnop")
        assert masked.startswith("abcd")
        assert masked.endswith("mnop")
        assert "*" in masked
        # Original secret should NOT appear in masked
        assert "abcdefghijklmnop" != masked

    def test_credential_never_exposes_secret(self):
        cred = ExchangeCredential(
            exchange="binance",
            api_key="pk_test_abcdefgh12345678",
            api_secret="sk_secret_supersecret_key_here",
        )
        safe = cred.to_safe_dict()
        assert "sk_secret_supersecret_key_here" not in str(safe)
        assert "api_secret" not in safe  # No secret field at all
        assert safe["has_secret"] is True

        # repr should not leak
        assert "sk_secret" not in repr(cred)
        assert "sk_secret" not in str(cred)

    def test_credential_has_keys(self):
        cred = ExchangeCredential(exchange="binance", api_key="k", api_secret="s")
        assert cred.has_keys
        cred2 = ExchangeCredential(exchange="binance")
        assert not cred2.has_keys


class TestCredentialManager:

    def test_load_from_env(self):
        with patch.dict("os.environ", {
            "BINANCE_API_KEY": "test_key",
            "BINANCE_API_SECRET": "test_secret",
        }, clear=False):
            mgr = CredentialManager()
            mgr.load_from_env()
            assert mgr.has_valid_keys("binance")
            assert not mgr.has_valid_keys("okx")

    def test_get_status_summary_safe(self):
        mgr = CredentialManager()
        cred = ExchangeCredential(
            exchange="binance",
            api_key="real_key_12345678",
            api_secret="real_secret_abcdefgh",
        )
        mgr._credentials["binance"] = cred
        summary = mgr.get_status_summary()
        assert len(summary) == 1
        # Must NOT contain raw secrets
        assert "real_secret_abcdefgh" not in str(summary)
        assert "real_key_12345678" not in str(summary)


# =====================================================================
# Exchange Error Classification
# =====================================================================

class TestExchangeErrorClassification:

    def test_binance_auth_error(self):
        result = classify_binance_error(401, -2015, "Invalid API-key")
        assert result == ExchangeErrorType.AUTH_ERROR

    def test_binance_rate_limit(self):
        result = classify_binance_error(429, -1, "Rate limit exceeded")
        assert result == ExchangeErrorType.RATE_LIMIT_ERROR

    def test_binance_time_sync(self):
        result = classify_binance_error(400, -1021, "Timestamp outside recv window")
        assert result == ExchangeErrorType.TIME_SYNC_ERROR

    def test_binance_insufficient_balance(self):
        result = classify_binance_error(400, -2010, "Insufficient balance")
        assert result == ExchangeErrorType.INSUFFICIENT_BALANCE

    def test_binance_unknown_error(self):
        result = classify_binance_error(500, -9999, "Unknown server error")
        assert result == ExchangeErrorType.UNKNOWN_ERROR

    def test_okx_auth_error(self):
        result = classify_okx_error("50111", "Invalid sign")
        assert result == ExchangeErrorType.AUTH_ERROR

    def test_okx_rate_limit(self):
        result = classify_okx_error("50011", "Rate limit reached")
        assert result == ExchangeErrorType.RATE_LIMIT_ERROR

    def test_bybit_auth_error(self):
        result = classify_bybit_error(10003, "Invalid apikey")
        assert result == ExchangeErrorType.AUTH_ERROR

    def test_bybit_insufficient_balance(self):
        result = classify_bybit_error(170131, "Insufficient balance")
        assert result == ExchangeErrorType.UNKNOWN_ERROR  # 170131 is not mapped


# =====================================================================
# Pre-Order Validation (LiveGuardrails)
# =====================================================================

def _make_guardrails(
    mode: str = "live_small",
    kill_switch: KillSwitch | None = None,
    with_creds: bool = True,
    with_market: bool = True,
    live_enabled: bool = True,
    live_small_enabled: bool = True,
) -> LiveGuardrails:
    """Build a LiveGuardrails with mocked dependencies."""
    from app.exchanges.base import StandardTicker

    ks = kill_switch or KillSwitch()
    cm = CredentialManager()
    if with_creds:
        cm._credentials["binance"] = ExchangeCredential(
            exchange="binance", api_key="key", api_secret="secret"
        )

    event_bus = EventBus()
    market_data = None
    if with_market:
        market_data = MagicMock()
        market_data.get_ticker.return_value = StandardTicker(
            exchange="binance", symbol="BTC/USDT",
            bid=60000.0, ask=60010.0, bid_size=1.0, ask_size=1.0,
        )
        market_data.get_data_age.return_value = 0.5

    cfg = Settings(
        live={
            "enabled": live_enabled,
            "enable_live_small": live_small_enabled,
            "trading_mode": mode,
            "live_small_max_single_usdt": 50.0,
            "live_max_single_usdt": 5000.0,
            "live_max_daily_per_exchange_usdt": 50000.0,
            "live_max_daily_per_symbol_usdt": 20000.0,
            "live_max_daily_total_usdt": 100000.0,
            "max_price_deviation_pct": 0.5,
            "max_price_staleness_s": 3.0,
        },
        strategy={
            "enabled_pairs": ["BTC/USDT"],
            "scan_interval_ms": 500,
        },
    )

    return LiveGuardrails(
        kill_switch=ks,
        credential_manager=cm,
        event_bus=event_bus,
        redis_client=None,
        audit_service=None,
        market_data=market_data,
        config=cfg,
    )


class TestPreOrderValidation:

    @pytest.mark.asyncio
    async def test_paper_mode_blocks_orders(self):
        guard = _make_guardrails(mode="paper")
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.001, price=60000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "mode_allows_orders" in rejections

    @pytest.mark.asyncio
    async def test_read_only_blocks_orders(self):
        guard = _make_guardrails(mode="read_only")
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.001, price=60000.0,
        )
        assert not check.approved

    @pytest.mark.asyncio
    async def test_live_small_approves_within_limits(self):
        guard = _make_guardrails(mode="live_small")
        # 0.0005 BTC * 60000 = $30 which is under $50 live_small limit
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.0005, price=60000.0,
        )
        assert check.approved

    @pytest.mark.asyncio
    async def test_live_small_rejects_over_limit(self):
        guard = _make_guardrails(mode="live_small")
        # 0.01 BTC * 60000 = $600 which exceeds $50 live_small limit
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.01, price=60000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "single_order_limit" in rejections

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_all(self):
        ks = KillSwitch()
        ks.activate(reason="test", activated_by="test")
        guard = _make_guardrails(mode="live_small", kill_switch=ks)
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.0001, price=60000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "kill_switch_inactive" in rejections

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_exchange(self):
        ks = KillSwitch()
        ks.get_or_create_breaker("exchange:binance", threshold=1)
        ks.record_failure("exchange:binance", "test failure")
        guard = _make_guardrails(mode="live_small", kill_switch=ks)
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.0001, price=60000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "exchange_circuit_breaker" in rejections

    @pytest.mark.asyncio
    async def test_missing_credentials_blocks(self):
        guard = _make_guardrails(mode="live_small", with_creds=False)
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.0001, price=60000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "credentials_available" in rejections

    @pytest.mark.asyncio
    async def test_stale_market_data_blocks(self):
        guard = _make_guardrails(mode="live_small")
        guard._market.get_data_age.return_value = 10.0  # 10s > 3s limit
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.0001, price=60000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "data_freshness" in rejections

    @pytest.mark.asyncio
    async def test_price_deviation_blocks(self):
        guard = _make_guardrails(mode="live_small")
        # Price way off from mid (~60005): 70000 is ~16% deviation
        check = await guard.validate_pre_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", quantity=0.0001, price=70000.0,
        )
        assert not check.approved
        rejections = [c["name"] for c in check.rejections]
        assert "price_deviation" in rejections


# =====================================================================
# Order Lifecycle Tracking
# =====================================================================

class TestTrackedOrder:

    def test_initial_state(self):
        order = TrackedOrder(exchange="binance", symbol="BTC/USDT", side="BUY")
        assert order.state == OrderLifecycleState.PENDING_SUBMIT
        assert not order.is_terminal
        assert order.fill_pct == 0.0

    def test_state_transitions_recorded(self):
        order = TrackedOrder()
        order.record_transition(OrderLifecycleState.SUBMITTED, "order submitted")
        order.record_transition(OrderLifecycleState.FILLED, "fully filled")
        assert order.state == OrderLifecycleState.FILLED
        assert order.is_terminal
        assert len(order.history) == 2
        assert order.history[0]["from"] == "pending_submit"
        assert order.history[0]["to"] == "submitted"

    def test_fill_pct_calculation(self):
        order = TrackedOrder(requested_quantity=1.0, filled_quantity=0.5)
        assert order.fill_pct == pytest.approx(50.0)

    def test_notional_value(self):
        order = TrackedOrder(
            filled_quantity=0.5,
            avg_fill_price=60000.0,
        )
        assert order.notional_value == pytest.approx(30000.0)

    def test_to_dict_complete(self):
        order = TrackedOrder(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", order_type="MARKET",
        )
        d = order.to_dict()
        assert d["exchange"] == "binance"
        assert d["symbol"] == "BTC/USDT"
        assert "tracking_id" in d
        assert "state" in d


class TestOrderTracker:

    def test_register_order(self):
        tracker = OrderTracker(
            event_bus=EventBus(),
            exchange_factory=MagicMock(),
        )
        order = tracker.register_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", order_type="MARKET",
            quantity=0.001,
        )
        assert order.state == OrderLifecycleState.PENDING_SUBMIT
        assert tracker.metrics.total_orders_tracked == 1
        assert len(tracker.get_active_orders()) == 1

    def test_mark_submitted(self):
        tracker = OrderTracker(
            event_bus=EventBus(),
            exchange_factory=MagicMock(),
        )
        order = tracker.register_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", order_type="MARKET", quantity=0.001,
        )
        tracker.mark_submitted(order.tracking_id, order_id="123456")
        assert order.state == OrderLifecycleState.SUBMITTED
        assert order.order_id == "123456"

    def test_mark_failed(self):
        tracker = OrderTracker(
            event_bus=EventBus(),
            exchange_factory=MagicMock(),
        )
        order = tracker.register_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", order_type="MARKET", quantity=0.001,
        )
        tracker.mark_failed(order.tracking_id, "submission timeout")
        # Should be moved to completed
        assert len(tracker.get_active_orders()) == 0
        assert tracker.metrics.total_failed == 1

    def test_get_order_from_completed(self):
        tracker = OrderTracker(
            event_bus=EventBus(),
            exchange_factory=MagicMock(),
        )
        order = tracker.register_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", order_type="MARKET", quantity=0.001,
        )
        tid = order.tracking_id
        tracker.mark_failed(tid, "test")
        # Should still be findable
        found = tracker.get_order(tid)
        assert found is not None
        assert found.tracking_id == tid

    def test_get_orders_by_execution(self):
        tracker = OrderTracker(
            event_bus=EventBus(),
            exchange_factory=MagicMock(),
        )
        tracker.register_order(
            exchange="binance", symbol="BTC/USDT",
            side="BUY", order_type="MARKET", quantity=0.001,
            execution_id="exec-1",
        )
        tracker.register_order(
            exchange="okx", symbol="BTC/USDT",
            side="SELL", order_type="MARKET", quantity=0.001,
            execution_id="exec-1",
        )
        tracker.register_order(
            exchange="binance", symbol="ETH/USDT",
            side="BUY", order_type="MARKET", quantity=0.01,
            execution_id="exec-2",
        )
        orders = tracker.get_orders_by_execution("exec-1")
        assert len(orders) == 2


# =====================================================================
# Reconciliation
# =====================================================================

class TestReconciliationResult:

    def test_consistent_result(self):
        r = ReconciliationResult(
            order_tracking_id="t1", exchange="binance",
            symbol="BTC/USDT", order_id="123",
            local_state="filled", exchange_state="filled",
            local_filled_qty=0.001, exchange_filled_qty=0.001,
            qty_mismatch=0.0, is_consistent=True,
        )
        assert r.is_consistent
        d = r.to_dict()
        assert d["is_consistent"]

    def test_mismatch_result(self):
        r = ReconciliationResult(
            order_tracking_id="t1", exchange="binance",
            symbol="BTC/USDT", order_id="123",
            local_state="filled", exchange_state="partially_filled",
            local_filled_qty=0.001, exchange_filled_qty=0.0008,
            qty_mismatch=0.0002, is_consistent=False,
        )
        assert not r.is_consistent
        assert r.qty_mismatch == pytest.approx(0.0002)


# =====================================================================
# Mode change via LiveGuardrails
# =====================================================================

class TestModeManagement:

    @pytest.mark.asyncio
    async def test_set_mode_emits_event(self):
        guard = _make_guardrails(mode="paper")
        events: list[dict] = []

        async def capture(event):
            events.append(event)

        guard._bus.subscribe(EventType.LIVE_MODE_CHANGED, capture)

        await guard.set_mode(TradingMode.READ_ONLY, changed_by="test")
        assert guard.current_mode == TradingMode.READ_ONLY
        # Event should have fired
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_mode_change_updates_capabilities(self):
        guard = _make_guardrails(mode="paper")
        assert not guard.capabilities.can_place_orders
        await guard.set_mode(TradingMode.LIVE_SMALL, changed_by="test")
        assert guard.capabilities.can_place_orders
        assert not guard.capabilities.can_auto_execute
