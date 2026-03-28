"""
Seed data script for the arbitrage system.

Creates initial exchanges, symbols, strategy configs, balances, and sample
records. Idempotent -- safe to run multiple times.

Usage:
    python -m app.db.seed
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory, engine
from app.models.exchange import Exchange
from app.models.symbol import ExchangeSymbol
from app.models.balance import Balance
from app.models.strategy import StrategyConfig
from app.models.opportunity import ArbitrageOpportunity, OpportunityStatus, StrategyType
from app.models.execution import (
    ExecutionLeg,
    ExecutionMode,
    ExecutionPlan,
    ExecutionPlanStatus,
    LegSide,
    LegStatus,
)
from app.models.analytics import PnlRecord


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_or_create(session: AsyncSession, model, defaults: dict, **lookup):
    """Return existing row or create a new one. Lookup kwargs are the unique filter."""
    stmt = select(model)
    for k, v in lookup.items():
        stmt = stmt.where(getattr(model, k) == v)
    result = await session.execute(stmt)
    instance = result.scalars().first()
    if instance is not None:
        return instance, False
    instance = model(**lookup, **defaults)
    session.add(instance)
    await session.flush()
    return instance, True


# ---------------------------------------------------------------------------
# Exchanges
# ---------------------------------------------------------------------------

EXCHANGES = [
    {
        "name": "binance",
        "display_name": "Binance",
        "is_active": True,
        "api_status": "CONNECTED",
        "ws_status": "CONNECTED",
        "config_json": {
            "rate_limit_per_minute": 1200,
            "ws_url": "wss://stream.binance.com:9443/ws",
            "rest_url": "https://api.binance.com",
            "recv_window": 5000,
            "default_order_type": "LIMIT",
        },
    },
    {
        "name": "okx",
        "display_name": "OKX",
        "is_active": True,
        "api_status": "CONNECTED",
        "ws_status": "CONNECTED",
        "config_json": {
            "rate_limit_per_minute": 600,
            "ws_url": "wss://ws.okx.com:8443/ws/v5/public",
            "rest_url": "https://www.okx.com",
            "recv_window": 5000,
            "default_order_type": "LIMIT",
        },
    },
    {
        "name": "bybit",
        "display_name": "Bybit",
        "is_active": True,
        "api_status": "CONNECTED",
        "ws_status": "CONNECTED",
        "config_json": {
            "rate_limit_per_minute": 600,
            "ws_url": "wss://stream.bybit.com/v5/public/spot",
            "rest_url": "https://api.bybit.com",
            "recv_window": 5000,
            "default_order_type": "LIMIT",
        },
    },
]


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------

SYMBOLS = [
    {
        "symbol": "BTC/USDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "price_precision": 2,
        "quantity_precision": 6,
        "min_quantity": Decimal("0.000001"),
        "max_quantity": Decimal("9999.0"),
        "min_notional": Decimal("10.0"),
        "tick_size": Decimal("0.01"),
        "step_size": Decimal("0.000001"),
        "maker_fee": Decimal("0.001"),
        "taker_fee": Decimal("0.001"),
    },
    {
        "symbol": "ETH/USDT",
        "base_asset": "ETH",
        "quote_asset": "USDT",
        "price_precision": 2,
        "quantity_precision": 5,
        "min_quantity": Decimal("0.00001"),
        "max_quantity": Decimal("99999.0"),
        "min_notional": Decimal("10.0"),
        "tick_size": Decimal("0.01"),
        "step_size": Decimal("0.00001"),
        "maker_fee": Decimal("0.001"),
        "taker_fee": Decimal("0.001"),
    },
    {
        "symbol": "SOL/USDT",
        "base_asset": "SOL",
        "quote_asset": "USDT",
        "price_precision": 4,
        "quantity_precision": 2,
        "min_quantity": Decimal("0.01"),
        "max_quantity": Decimal("999999.0"),
        "min_notional": Decimal("5.0"),
        "tick_size": Decimal("0.0001"),
        "step_size": Decimal("0.01"),
        "maker_fee": Decimal("0.001"),
        "taker_fee": Decimal("0.001"),
    },
    {
        "symbol": "XRP/USDT",
        "base_asset": "XRP",
        "quote_asset": "USDT",
        "price_precision": 5,
        "quantity_precision": 1,
        "min_quantity": Decimal("1.0"),
        "max_quantity": Decimal("9999999.0"),
        "min_notional": Decimal("5.0"),
        "tick_size": Decimal("0.00001"),
        "step_size": Decimal("0.1"),
        "maker_fee": Decimal("0.001"),
        "taker_fee": Decimal("0.001"),
    },
    {
        "symbol": "DOGE/USDT",
        "base_asset": "DOGE",
        "quote_asset": "USDT",
        "price_precision": 6,
        "quantity_precision": 0,
        "min_quantity": Decimal("1.0"),
        "max_quantity": Decimal("99999999.0"),
        "min_notional": Decimal("5.0"),
        "tick_size": Decimal("0.000001"),
        "step_size": Decimal("1.0"),
        "maker_fee": Decimal("0.001"),
        "taker_fee": Decimal("0.001"),
    },
]


# ---------------------------------------------------------------------------
# Initial balances per exchange
# ---------------------------------------------------------------------------

BALANCES = [
    {"asset": "USDT", "free": Decimal("10000.0"), "locked": Decimal("0.0"), "total": Decimal("10000.0"), "usd_value": Decimal("10000.0")},
    {"asset": "BTC", "free": Decimal("0.5"), "locked": Decimal("0.0"), "total": Decimal("0.5"), "usd_value": Decimal("33500.0")},
    {"asset": "ETH", "free": Decimal("5.0"), "locked": Decimal("0.0"), "total": Decimal("5.0"), "usd_value": Decimal("17500.0")},
    {"asset": "SOL", "free": Decimal("100.0"), "locked": Decimal("0.0"), "total": Decimal("100.0"), "usd_value": Decimal("14000.0")},
    {"asset": "XRP", "free": Decimal("5000.0"), "locked": Decimal("0.0"), "total": Decimal("5000.0"), "usd_value": Decimal("3000.0")},
    {"asset": "DOGE", "free": Decimal("20000.0"), "locked": Decimal("0.0"), "total": Decimal("20000.0"), "usd_value": Decimal("3200.0")},
]


# ---------------------------------------------------------------------------
# Strategy configs
# ---------------------------------------------------------------------------

STRATEGY_CONFIGS = [
    {
        "name": "Cross-Exchange Spot Arbitrage",
        "strategy_type": StrategyType.CROSS_EXCHANGE,
        "is_enabled": True,
        "exchanges": ["binance", "okx", "bybit"],
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"],
        "min_profit_threshold_pct": Decimal("0.15"),
        "max_order_value_usdt": Decimal("5000.0"),
        "max_concurrent_executions": 3,
        "min_depth_usdt": Decimal("10000.0"),
        "max_slippage_pct": Decimal("0.05"),
        "scan_interval_ms": 500,
        "blacklist_symbols": [],
        "whitelist_symbols": None,
        "custom_params": {
            "min_spread_bps": 15,
            "use_taker_for_entry": True,
            "hedge_timeout_ms": 3000,
        },
    },
    {
        "name": "Triangular Arbitrage",
        "strategy_type": StrategyType.TRIANGULAR,
        "is_enabled": True,
        "exchanges": ["binance"],
        "symbols": ["BTC/USDT", "ETH/USDT", "ETH/BTC"],
        "min_profit_threshold_pct": Decimal("0.10"),
        "max_order_value_usdt": Decimal("3000.0"),
        "max_concurrent_executions": 2,
        "min_depth_usdt": Decimal("5000.0"),
        "max_slippage_pct": Decimal("0.03"),
        "scan_interval_ms": 300,
        "blacklist_symbols": [],
        "whitelist_symbols": None,
        "custom_params": {
            "triangle_paths": [
                ["USDT", "BTC", "ETH", "USDT"],
                ["USDT", "ETH", "BTC", "USDT"],
            ],
        },
    },
    {
        "name": "Futures-Spot Arbitrage",
        "strategy_type": StrategyType.FUTURES_SPOT,
        "is_enabled": False,
        "exchanges": ["binance", "okx"],
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "min_profit_threshold_pct": Decimal("0.20"),
        "max_order_value_usdt": Decimal("10000.0"),
        "max_concurrent_executions": 1,
        "min_depth_usdt": Decimal("20000.0"),
        "max_slippage_pct": Decimal("0.05"),
        "scan_interval_ms": 1000,
        "blacklist_symbols": [],
        "whitelist_symbols": None,
        "custom_params": {
            "funding_rate_threshold": 0.01,
            "basis_threshold_pct": 0.15,
            "placeholder": True,
        },
    },
    {
        "name": "Statistical Arbitrage",
        "strategy_type": StrategyType.CROSS_EXCHANGE,
        "is_enabled": False,
        "exchanges": ["binance", "okx", "bybit"],
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "min_profit_threshold_pct": Decimal("0.25"),
        "max_order_value_usdt": Decimal("2000.0"),
        "max_concurrent_executions": 1,
        "min_depth_usdt": Decimal("15000.0"),
        "max_slippage_pct": Decimal("0.04"),
        "scan_interval_ms": 2000,
        "blacklist_symbols": [],
        "whitelist_symbols": None,
        "custom_params": {
            "lookback_window": 100,
            "z_score_entry": 2.0,
            "z_score_exit": 0.5,
            "placeholder": True,
        },
    },
]


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

async def run_seed() -> None:
    """Populate the database with initial seed data (idempotent)."""
    async with async_session_factory() as session:
        async with session.begin():
            # ---- Exchanges ----
            exchange_map: dict[str, Exchange] = {}
            for ex_data in EXCHANGES:
                name = ex_data["name"]
                ex, created = await _get_or_create(
                    session,
                    Exchange,
                    defaults={
                        "display_name": ex_data["display_name"],
                        "is_active": ex_data["is_active"],
                        "api_status": ex_data["api_status"],
                        "ws_status": ex_data["ws_status"],
                        "config_json": ex_data["config_json"],
                    },
                    name=name,
                )
                exchange_map[name] = ex
                status = "CREATED" if created else "EXISTS"
                print(f"  Exchange {name}: {status}")

            # ---- Exchange Symbols ----
            for ex_name, ex in exchange_map.items():
                for sym_data in SYMBOLS:
                    sym_copy = dict(sym_data)
                    symbol_str = sym_copy.pop("symbol")
                    _, created = await _get_or_create(
                        session,
                        ExchangeSymbol,
                        defaults={
                            **sym_copy,
                            "is_active": True,
                            "status": "TRADING",
                        },
                        exchange_id=ex.id,
                        symbol=symbol_str,
                    )
                    status = "CREATED" if created else "EXISTS"
                    print(f"  Symbol {ex_name}/{symbol_str}: {status}")

            # ---- Balances ----
            for ex_name, ex in exchange_map.items():
                for bal_data in BALANCES:
                    _, created = await _get_or_create(
                        session,
                        Balance,
                        defaults={
                            "free": bal_data["free"],
                            "locked": bal_data["locked"],
                            "total": bal_data["total"],
                            "usd_value": bal_data["usd_value"],
                        },
                        exchange_id=ex.id,
                        asset=bal_data["asset"],
                    )
                    status = "CREATED" if created else "EXISTS"
                    print(f"  Balance {ex_name}/{bal_data['asset']}: {status}")

            # ---- Strategy Configs ----
            for cfg in STRATEGY_CONFIGS:
                cfg_copy = dict(cfg)
                name = cfg_copy.pop("name")
                _, created = await _get_or_create(
                    session,
                    StrategyConfig,
                    defaults=cfg_copy,
                    name=name,
                )
                status = "CREATED" if created else "EXISTS"
                print(f"  Strategy '{name}': {status}")

            # ---- Sample Arbitrage Opportunities ----
            now = datetime.now(timezone.utc)

            opp1_id = uuid.uuid4()
            opp1, created = await _get_or_create(
                session,
                ArbitrageOpportunity,
                defaults={
                    "id": opp1_id,
                    "strategy_type": StrategyType.CROSS_EXCHANGE,
                    "symbols": ["BTC/USDT"],
                    "exchanges": ["binance", "okx"],
                    "buy_exchange": "binance",
                    "sell_exchange": "okx",
                    "buy_price": Decimal("67100.50"),
                    "sell_price": Decimal("67250.80"),
                    "spread_pct": Decimal("0.2240"),
                    "theoretical_profit_pct": Decimal("0.2240"),
                    "estimated_net_profit_pct": Decimal("0.1240"),
                    "estimated_slippage_pct": Decimal("0.0100"),
                    "executable_quantity": Decimal("0.050000"),
                    "executable_value_usdt": Decimal("3355.0"),
                    "buy_fee_pct": Decimal("0.001000"),
                    "sell_fee_pct": Decimal("0.001000"),
                    "confidence_score": Decimal("0.8500"),
                    "risk_flags": {},
                    "orderbook_depth_buy": Decimal("150000.0"),
                    "orderbook_depth_sell": Decimal("120000.0"),
                    "is_executable": True,
                    "status": OpportunityStatus.EXECUTED,
                    "detected_at": now,
                },
                buy_exchange="binance",
                sell_exchange="okx",
                spread_pct=Decimal("0.2240"),
            )
            print(f"  Opportunity BTC binance->okx 0.224%: {'CREATED' if created else 'EXISTS'}")

            opp2_id = uuid.uuid4()
            opp2, created = await _get_or_create(
                session,
                ArbitrageOpportunity,
                defaults={
                    "id": opp2_id,
                    "strategy_type": StrategyType.CROSS_EXCHANGE,
                    "symbols": ["ETH/USDT"],
                    "exchanges": ["okx", "bybit"],
                    "buy_exchange": "okx",
                    "sell_exchange": "bybit",
                    "buy_price": Decimal("3480.20"),
                    "sell_price": Decimal("3488.50"),
                    "spread_pct": Decimal("0.2384"),
                    "theoretical_profit_pct": Decimal("0.2384"),
                    "estimated_net_profit_pct": Decimal("0.1384"),
                    "estimated_slippage_pct": Decimal("0.0080"),
                    "executable_quantity": Decimal("1.500000"),
                    "executable_value_usdt": Decimal("5220.30"),
                    "buy_fee_pct": Decimal("0.001000"),
                    "sell_fee_pct": Decimal("0.001000"),
                    "confidence_score": Decimal("0.7800"),
                    "risk_flags": {},
                    "orderbook_depth_buy": Decimal("80000.0"),
                    "orderbook_depth_sell": Decimal("95000.0"),
                    "is_executable": True,
                    "status": OpportunityStatus.EXECUTED,
                    "detected_at": now,
                },
                buy_exchange="okx",
                sell_exchange="bybit",
                spread_pct=Decimal("0.2384"),
            )
            print(f"  Opportunity ETH okx->bybit 0.238%: {'CREATED' if created else 'EXISTS'}")

            opp3_id = uuid.uuid4()
            opp3, created = await _get_or_create(
                session,
                ArbitrageOpportunity,
                defaults={
                    "id": opp3_id,
                    "strategy_type": StrategyType.CROSS_EXCHANGE,
                    "symbols": ["SOL/USDT"],
                    "exchanges": ["bybit", "binance"],
                    "buy_exchange": "bybit",
                    "sell_exchange": "binance",
                    "buy_price": Decimal("139.8500"),
                    "sell_price": Decimal("140.1200"),
                    "spread_pct": Decimal("0.1930"),
                    "theoretical_profit_pct": Decimal("0.1930"),
                    "estimated_net_profit_pct": Decimal("0.0930"),
                    "estimated_slippage_pct": Decimal("0.0120"),
                    "executable_quantity": Decimal("20.000000"),
                    "executable_value_usdt": Decimal("2797.0"),
                    "buy_fee_pct": Decimal("0.001000"),
                    "sell_fee_pct": Decimal("0.001000"),
                    "confidence_score": Decimal("0.7200"),
                    "risk_flags": {"low_depth": "sell side below threshold"},
                    "orderbook_depth_buy": Decimal("60000.0"),
                    "orderbook_depth_sell": Decimal("40000.0"),
                    "is_executable": False,
                    "rejection_reason": "Sell-side orderbook depth below minimum threshold",
                    "status": OpportunityStatus.REJECTED,
                    "detected_at": now,
                },
                buy_exchange="bybit",
                sell_exchange="binance",
                spread_pct=Decimal("0.1930"),
            )
            print(f"  Opportunity SOL bybit->binance 0.193%: {'CREATED' if created else 'EXISTS'}")

            # ---- Sample Execution Plans & Legs ----
            plan1_id = uuid.uuid4()
            plan1, created = await _get_or_create(
                session,
                ExecutionPlan,
                defaults={
                    "id": plan1_id,
                    "strategy_type": StrategyType.CROSS_EXCHANGE,
                    "mode": ExecutionMode.PAPER,
                    "target_quantity": Decimal("0.050000"),
                    "target_value_usdt": Decimal("3355.0"),
                    "planned_profit_pct": Decimal("0.1240"),
                    "status": ExecutionPlanStatus.COMPLETED,
                    "started_at": now,
                    "completed_at": now,
                    "actual_profit_pct": Decimal("0.1100"),
                    "actual_profit_usdt": Decimal("3.69"),
                    "execution_time_ms": 1250,
                    "metadata_json": {"paper_mode": True, "version": "1.0"},
                },
                opportunity_id=opp1.id,
            )
            print(f"  ExecutionPlan for BTC opp: {'CREATED' if created else 'EXISTS'}")

            if created:
                # Leg 0 -- BUY on Binance
                leg0 = ExecutionLeg(
                    id=uuid.uuid4(),
                    execution_plan_id=plan1.id,
                    leg_index=0,
                    exchange="binance",
                    symbol="BTC/USDT",
                    side=LegSide.BUY,
                    planned_price=Decimal("67100.50"),
                    planned_quantity=Decimal("0.050000"),
                    actual_price=Decimal("67102.30"),
                    actual_quantity=Decimal("0.050000"),
                    fee=Decimal("3.355115"),
                    fee_asset="USDT",
                    slippage_pct=Decimal("0.002700"),
                    status=LegStatus.FILLED,
                    submitted_at=now,
                    filled_at=now,
                )
                session.add(leg0)

                # Leg 1 -- SELL on OKX
                leg1 = ExecutionLeg(
                    id=uuid.uuid4(),
                    execution_plan_id=plan1.id,
                    leg_index=1,
                    exchange="okx",
                    symbol="BTC/USDT",
                    side=LegSide.SELL,
                    planned_price=Decimal("67250.80"),
                    planned_quantity=Decimal("0.050000"),
                    actual_price=Decimal("67248.10"),
                    actual_quantity=Decimal("0.050000"),
                    fee=Decimal("3.362405"),
                    fee_asset="USDT",
                    slippage_pct=Decimal("0.004000"),
                    status=LegStatus.FILLED,
                    submitted_at=now,
                    filled_at=now,
                )
                session.add(leg1)
                print("  ExecutionLegs for BTC plan: CREATED")

            plan2_id = uuid.uuid4()
            plan2, created = await _get_or_create(
                session,
                ExecutionPlan,
                defaults={
                    "id": plan2_id,
                    "strategy_type": StrategyType.CROSS_EXCHANGE,
                    "mode": ExecutionMode.PAPER,
                    "target_quantity": Decimal("1.500000"),
                    "target_value_usdt": Decimal("5220.30"),
                    "planned_profit_pct": Decimal("0.1384"),
                    "status": ExecutionPlanStatus.COMPLETED,
                    "started_at": now,
                    "completed_at": now,
                    "actual_profit_pct": Decimal("0.1200"),
                    "actual_profit_usdt": Decimal("6.26"),
                    "execution_time_ms": 980,
                    "metadata_json": {"paper_mode": True, "version": "1.0"},
                },
                opportunity_id=opp2.id,
            )
            print(f"  ExecutionPlan for ETH opp: {'CREATED' if created else 'EXISTS'}")

            if created:
                leg2 = ExecutionLeg(
                    id=uuid.uuid4(),
                    execution_plan_id=plan2.id,
                    leg_index=0,
                    exchange="okx",
                    symbol="ETH/USDT",
                    side=LegSide.BUY,
                    planned_price=Decimal("3480.20"),
                    planned_quantity=Decimal("1.500000"),
                    actual_price=Decimal("3480.50"),
                    actual_quantity=Decimal("1.500000"),
                    fee=Decimal("5.220750"),
                    fee_asset="USDT",
                    slippage_pct=Decimal("0.008600"),
                    status=LegStatus.FILLED,
                    submitted_at=now,
                    filled_at=now,
                )
                session.add(leg2)

                leg3 = ExecutionLeg(
                    id=uuid.uuid4(),
                    execution_plan_id=plan2.id,
                    leg_index=1,
                    exchange="bybit",
                    symbol="ETH/USDT",
                    side=LegSide.SELL,
                    planned_price=Decimal("3488.50"),
                    planned_quantity=Decimal("1.500000"),
                    actual_price=Decimal("3488.20"),
                    actual_quantity=Decimal("1.500000"),
                    fee=Decimal("5.232300"),
                    fee_asset="USDT",
                    slippage_pct=Decimal("0.008600"),
                    status=LegStatus.FILLED,
                    submitted_at=now,
                    filled_at=now,
                )
                session.add(leg3)
                print("  ExecutionLegs for ETH plan: CREATED")

            # ---- Sample PnL Records ----
            # Check if we already have pnl records for the BTC execution
            existing_pnl = await session.execute(
                select(PnlRecord).where(PnlRecord.execution_id == plan1.id)
            )
            if existing_pnl.scalars().first() is None:
                pnl1 = PnlRecord(
                    id=uuid.uuid4(),
                    execution_id=plan1.id,
                    strategy_type=StrategyType.CROSS_EXCHANGE,
                    exchange_buy="binance",
                    exchange_sell="okx",
                    symbol="BTC/USDT",
                    gross_profit_usdt=Decimal("7.29"),
                    fees_usdt=Decimal("6.72"),
                    net_profit_usdt=Decimal("3.69"),
                    slippage_usdt=Decimal("0.18"),
                    execution_time_ms=1250,
                    mode=ExecutionMode.PAPER,
                )
                session.add(pnl1)
                print("  PnL record for BTC execution: CREATED")
            else:
                print("  PnL record for BTC execution: EXISTS")

            existing_pnl2 = await session.execute(
                select(PnlRecord).where(PnlRecord.execution_id == plan2.id)
            )
            if existing_pnl2.scalars().first() is None:
                pnl2 = PnlRecord(
                    id=uuid.uuid4(),
                    execution_id=plan2.id,
                    strategy_type=StrategyType.CROSS_EXCHANGE,
                    exchange_buy="okx",
                    exchange_sell="bybit",
                    symbol="ETH/USDT",
                    gross_profit_usdt=Decimal("11.55"),
                    fees_usdt=Decimal("10.45"),
                    net_profit_usdt=Decimal("6.26"),
                    slippage_usdt=Decimal("0.65"),
                    execution_time_ms=980,
                    mode=ExecutionMode.PAPER,
                )
                session.add(pnl2)
                print("  PnL record for ETH execution: CREATED")
            else:
                print("  PnL record for ETH execution: EXISTS")

            # A third standalone PnL record (no execution link, simulating a historical import)
            existing_pnl3 = await session.execute(
                select(PnlRecord).where(
                    PnlRecord.symbol == "SOL/USDT",
                    PnlRecord.exchange_buy == "bybit",
                    PnlRecord.exchange_sell == "binance",
                )
            )
            if existing_pnl3.scalars().first() is None:
                pnl3 = PnlRecord(
                    id=uuid.uuid4(),
                    execution_id=None,
                    strategy_type=StrategyType.CROSS_EXCHANGE,
                    exchange_buy="bybit",
                    exchange_sell="binance",
                    symbol="SOL/USDT",
                    gross_profit_usdt=Decimal("4.20"),
                    fees_usdt=Decimal("2.80"),
                    net_profit_usdt=Decimal("1.40"),
                    slippage_usdt=Decimal("0.32"),
                    execution_time_ms=1500,
                    mode=ExecutionMode.PAPER,
                )
                session.add(pnl3)
                print("  PnL record for SOL (historical): CREATED")
            else:
                print("  PnL record for SOL (historical): EXISTS")

        print("\nSeed complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    try:
        await run_seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
