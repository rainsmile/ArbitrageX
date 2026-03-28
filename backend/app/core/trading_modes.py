"""Trading mode definitions and permission boundaries."""
from __future__ import annotations
from enum import StrEnum
from dataclasses import dataclass, field


class TradingMode(StrEnum):
    MOCK = "mock"           # Pure mock, no real exchange access
    READ_ONLY = "read_only" # Real market data, no orders
    PAPER = "paper"         # Real data + simulated execution
    SIMULATION = "simulation"  # Enhanced simulation with orderbook modeling
    LIVE_SMALL = "live_small"  # Real orders, strict limits
    LIVE = "live"           # Full live trading


@dataclass(frozen=True)
class ModeCapabilities:
    """What each mode is allowed to do."""
    can_read_public_data: bool = False
    can_read_account: bool = False
    can_place_orders: bool = False
    can_cancel_orders: bool = False
    can_auto_execute: bool = False
    max_single_order_usdt: float = 0.0
    max_daily_notional_usdt: float = 0.0
    requires_api_keys: bool = False
    requires_trading_permission: bool = False
    audit_level: str = "standard"  # standard | elevated | critical


MODE_CAPABILITIES: dict[TradingMode, ModeCapabilities] = {
    TradingMode.MOCK: ModeCapabilities(
        can_read_public_data=False, can_read_account=False,
        can_place_orders=False, can_cancel_orders=False,
        can_auto_execute=True, max_single_order_usdt=0,
        max_daily_notional_usdt=0, requires_api_keys=False,
        requires_trading_permission=False, audit_level="standard",
    ),
    TradingMode.READ_ONLY: ModeCapabilities(
        can_read_public_data=True, can_read_account=True,
        can_place_orders=False, can_cancel_orders=False,
        can_auto_execute=False, max_single_order_usdt=0,
        max_daily_notional_usdt=0, requires_api_keys=True,
        requires_trading_permission=False, audit_level="standard",
    ),
    TradingMode.PAPER: ModeCapabilities(
        can_read_public_data=True, can_read_account=True,
        can_place_orders=False, can_cancel_orders=False,
        can_auto_execute=True, max_single_order_usdt=0,
        max_daily_notional_usdt=0, requires_api_keys=False,
        requires_trading_permission=False, audit_level="standard",
    ),
    TradingMode.SIMULATION: ModeCapabilities(
        can_read_public_data=True, can_read_account=True,
        can_place_orders=False, can_cancel_orders=False,
        can_auto_execute=True, max_single_order_usdt=0,
        max_daily_notional_usdt=0, requires_api_keys=False,
        requires_trading_permission=False, audit_level="standard",
    ),
    TradingMode.LIVE_SMALL: ModeCapabilities(
        can_read_public_data=True, can_read_account=True,
        can_place_orders=True, can_cancel_orders=True,
        can_auto_execute=False,  # Manual trigger only by default
        max_single_order_usdt=100.0,
        max_daily_notional_usdt=1000.0,
        requires_api_keys=True,
        requires_trading_permission=True,
        audit_level="elevated",
    ),
    TradingMode.LIVE: ModeCapabilities(
        can_read_public_data=True, can_read_account=True,
        can_place_orders=True, can_cancel_orders=True,
        can_auto_execute=True,
        max_single_order_usdt=10000.0,
        max_daily_notional_usdt=100000.0,
        requires_api_keys=True,
        requires_trading_permission=True,
        audit_level="critical",
    ),
}


def get_capabilities(mode: TradingMode) -> ModeCapabilities:
    return MODE_CAPABILITIES[mode]


def is_live_mode(mode: TradingMode) -> bool:
    return mode in (TradingMode.LIVE_SMALL, TradingMode.LIVE)


def can_place_real_orders(mode: TradingMode) -> bool:
    return MODE_CAPABILITIES[mode].can_place_orders
