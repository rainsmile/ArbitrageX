"""Tests for the InventoryManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exchanges.base import StandardBalance
from app.services.inventory import BalanceSnapshot, InventoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_inventory_manager(
    exchange_balances: dict[str, dict[str, StandardBalance]] | None = None,
) -> InventoryManager:
    """Build an InventoryManager with mocked dependencies."""
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()

    redis_client = AsyncMock()
    redis_client.set_json = AsyncMock()

    session_factory = MagicMock()

    market_data = MagicMock()
    market_data.get_all_tickers = MagicMock(return_value={})
    market_data.get_ticker = MagicMock(return_value=None)

    # Build fake adapters
    adapters = {}
    if exchange_balances:
        for name, balances in exchange_balances.items():
            adapter = AsyncMock()
            adapter.get_balance = AsyncMock(return_value=balances)
            adapters[name] = adapter

    exchange_factory = MagicMock()
    exchange_factory.get_all = MagicMock(return_value=adapters)
    exchange_factory.get = MagicMock(side_effect=lambda n: adapters.get(n))

    mgr = InventoryManager(
        event_bus=event_bus,
        exchange_factory=exchange_factory,
        redis_client=redis_client,
        session_factory=session_factory,
        market_data=market_data,
    )
    return mgr


# ---------------------------------------------------------------------------
# Balance queries
# ---------------------------------------------------------------------------

class TestGetBalance:
    def test_returns_none_for_unknown(self):
        mgr = _build_inventory_manager()
        assert mgr.get_balance("binance", "BTC") is None

    @pytest.mark.asyncio
    async def test_refresh_all_populates_cache(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {
                "USDT": StandardBalance(asset="USDT", free=10_000.0, locked=0.0),
                "BTC": StandardBalance(asset="BTC", free=1.0, locked=0.5),
            },
        })
        await mgr.refresh_all()

        snap = mgr.get_balance("binance", "USDT")
        assert snap is not None
        assert isinstance(snap, BalanceSnapshot)
        assert snap.free == 10_000.0
        assert snap.total == 10_000.0

        btc = mgr.get_balance("binance", "BTC")
        assert btc is not None
        assert btc.free == 1.0
        assert btc.locked == 0.5
        assert btc.total == 1.5

    @pytest.mark.asyncio
    async def test_refresh_all_skips_zero_balance(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {
                "ZERO": StandardBalance(asset="ZERO", free=0.0, locked=0.0),
            },
        })
        await mgr.refresh_all()
        assert mgr.get_balance("binance", "ZERO") is None

    @pytest.mark.asyncio
    async def test_refresh_all_publishes_event(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=100.0, locked=0.0)},
        })
        await mgr.refresh_all()
        mgr._event_bus.publish.assert_awaited()


# ---------------------------------------------------------------------------
# Check sufficient balance
# ---------------------------------------------------------------------------

class TestCheckSufficientBalance:
    @pytest.mark.asyncio
    async def test_sufficient(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=10_000.0, locked=0.0)},
        })
        await mgr.refresh_all()
        assert mgr.check_sufficient_balance("binance", "USDT", 5_000.0) is True

    @pytest.mark.asyncio
    async def test_insufficient(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=100.0, locked=0.0)},
        })
        await mgr.refresh_all()
        assert mgr.check_sufficient_balance("binance", "USDT", 5_000.0) is False

    def test_unknown_exchange_returns_false(self):
        mgr = _build_inventory_manager()
        assert mgr.check_sufficient_balance("unknown", "USDT", 1.0) is False


# ---------------------------------------------------------------------------
# Exposure and summary
# ---------------------------------------------------------------------------

class TestExposureAndSummary:
    @pytest.mark.asyncio
    async def test_get_exposure_structure(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=10_000.0, locked=0.0)},
            "okx": {"USDT": StandardBalance(asset="USDT", free=5_000.0, locked=0.0)},
        })
        await mgr.refresh_all()

        exposure = mgr.get_exposure()
        assert "total_value_usdt" in exposure
        assert "per_exchange" in exposure
        assert "per_asset" in exposure
        assert "concentration_risk" in exposure
        assert isinstance(exposure["concentration_risk"], float)

    @pytest.mark.asyncio
    async def test_get_inventory_summary_structure(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=5_000.0, locked=0.0)},
        })
        await mgr.refresh_all()

        summary = mgr.get_inventory_summary()
        assert "total_value_usdt" in summary
        assert "exchange_count" in summary
        assert summary["exchange_count"] == 1
        assert "asset_count" in summary
        assert summary["asset_count"] == 1
        assert "allocations" in summary
        assert "stablecoin_balance" in summary

    def test_empty_exposure(self):
        mgr = _build_inventory_manager()
        exposure = mgr.get_exposure()
        assert exposure["total_value_usdt"] == 0.0
        assert exposure["concentration_risk"] == 0.0


# ---------------------------------------------------------------------------
# on_execution_completed
# ---------------------------------------------------------------------------

class TestOnExecutionCompleted:
    @pytest.mark.asyncio
    async def test_refreshes_specific_exchanges(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=10_000.0, locked=0.0)},
            "okx": {"USDT": StandardBalance(asset="USDT", free=5_000.0, locked=0.0)},
        })
        result = {"buy_exchange": "binance", "sell_exchange": "okx"}
        await mgr.on_execution_completed(result)

        # Event published
        mgr._event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_exchange_warns(self):
        mgr = _build_inventory_manager()
        # No exchanges in result -- should just warn and return
        await mgr.on_execution_completed({})


# ---------------------------------------------------------------------------
# Exchange allocation
# ---------------------------------------------------------------------------

class TestExchangeAllocation:
    @pytest.mark.asyncio
    async def test_allocation_percentages(self):
        mgr = _build_inventory_manager(exchange_balances={
            "binance": {"USDT": StandardBalance(asset="USDT", free=10_000.0, locked=0.0)},
        })
        await mgr.refresh_all()

        allocations = mgr.get_exchange_allocation()
        assert len(allocations) == 1
        assert allocations[0].exchange == "binance"
        # Only one exchange so 100%
        assert allocations[0].pct_of_total == pytest.approx(100.0)
