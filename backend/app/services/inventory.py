"""
InventoryManager -- tracks balances across exchanges, detects imbalances,
and generates rebalance suggestions.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.db.redis import RedisClient
from app.exchanges.base import StandardBalance
from app.exchanges.factory import ExchangeFactory
from app.services.market_data import MarketDataService


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BalanceSnapshot:
    """In-memory representation of a single exchange/asset balance."""
    exchange: str
    asset: str
    free: float
    locked: float
    total: float
    usd_value: float = 0.0
    updated_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class ExchangeAllocation:
    """Allocation breakdown for a single exchange."""
    exchange: str
    total_value_usdt: float = 0.0
    pct_of_total: float = 0.0
    assets: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ImbalanceInfo:
    """Describes an inventory imbalance for an asset across exchanges."""
    asset: str
    target_ratio: dict[str, float] = field(default_factory=dict)
    actual_ratio: dict[str, float] = field(default_factory=dict)
    deviation: dict[str, float] = field(default_factory=dict)
    total_amount: float = 0.0


@dataclass(slots=True)
class RebalanceSuggestion:
    """A suggested transfer to correct an imbalance."""
    asset: str
    from_exchange: str
    to_exchange: str
    suggested_quantity: float
    reason: str


# ---------------------------------------------------------------------------
# InventoryManager
# ---------------------------------------------------------------------------

class InventoryManager:
    """Periodically fetches and caches balances from all exchanges.

    Provides balance lookups, allocation breakdowns, imbalance detection,
    and rebalance suggestions.
    """

    def __init__(
        self,
        event_bus: EventBus,
        exchange_factory: ExchangeFactory,
        redis_client: RedisClient,
        session_factory: async_sessionmaker[AsyncSession],
        market_data: MarketDataService,
        config: Settings | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._exchange_factory = exchange_factory
        self._redis = redis_client
        self._session_factory = session_factory
        self._market_data = market_data
        self._cfg = config or settings

        # In-memory cache: (exchange, asset) -> BalanceSnapshot
        self._balances: dict[tuple[str, str], BalanceSnapshot] = {}
        self._last_refresh: float = 0.0
        self._refresh_interval_s: float = 30.0
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        # Do an initial fetch
        await self.refresh_all()
        self._task = asyncio.create_task(self._refresh_loop(), name="inventory-refresh")
        logger.info("InventoryManager started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("InventoryManager stopped")

    async def _refresh_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._refresh_interval_s)
                await self.refresh_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("Inventory refresh error")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    async def refresh_all(self) -> None:
        """Fetch balances from all exchanges and update caches."""
        adapters = self._exchange_factory.get_all()
        now = time.time()

        async def _fetch_exchange(name: str) -> dict[str, StandardBalance]:
            try:
                adapter = adapters[name]
                return await adapter.get_balance()
            except Exception:
                logger.opt(exception=True).warning("Failed to fetch balance from {}", name)
                return {}

        tasks = {name: _fetch_exchange(name) for name in adapters}
        results: dict[str, dict[str, StandardBalance]] = {}

        for name, coro in tasks.items():
            results[name] = await coro

        # Update in-memory and Redis caches
        for exchange_name, balances in results.items():
            for asset, balance in balances.items():
                if balance.total <= 0:
                    continue

                # Estimate USD value
                usd_value = self._estimate_usd_value(asset, balance.total)

                snapshot = BalanceSnapshot(
                    exchange=exchange_name,
                    asset=asset,
                    free=balance.free,
                    locked=balance.locked,
                    total=balance.total,
                    usd_value=usd_value,
                    updated_at=now,
                )
                self._balances[(exchange_name, asset)] = snapshot

                # Cache in Redis
                try:
                    await self._redis.set_json(
                        f"balance:{exchange_name}:{asset}",
                        {
                            "exchange": exchange_name,
                            "asset": asset,
                            "free": balance.free,
                            "locked": balance.locked,
                            "total": balance.total,
                            "usd_value": usd_value,
                            "ts": now,
                        },
                        ttl_s=120,
                    )
                except Exception:
                    logger.opt(exception=True).debug("Redis balance cache write failed")

        self._last_refresh = now

        # Publish event
        await self._event_bus.publish(
            EventType.BALANCE_UPDATED,
            {
                "exchanges": list(results.keys()),
                "total_assets": len(self._balances),
                "timestamp": now,
            },
        )

        logger.debug(
            "Inventory refreshed: {} exchanges, {} assets",
            len(results), len(self._balances),
        )

    def _estimate_usd_value(self, asset: str, amount: float) -> float:
        """Estimate the USD value of an asset amount using cached tickers."""
        if asset in ("USDT", "USDC", "BUSD", "DAI"):
            return amount

        # Try to find a ticker for asset/USDT on any exchange
        all_tickers = self._market_data.get_all_tickers()
        symbol = f"{asset}/USDT"

        for (exch, sym), ticker in all_tickers.items():
            if sym == symbol and ticker.last_price > 0:
                return amount * ticker.last_price

        # Fallback: check for asset/BTC and BTC/USDT
        btc_price = 0.0
        asset_btc_price = 0.0
        for (exch, sym), ticker in all_tickers.items():
            if sym == "BTC/USDT" and ticker.last_price > 0:
                btc_price = ticker.last_price
            if sym == f"{asset}/BTC" and ticker.last_price > 0:
                asset_btc_price = ticker.last_price

        if btc_price > 0 and asset_btc_price > 0:
            return amount * asset_btc_price * btc_price

        return 0.0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_balance(self, exchange: str, asset: str) -> BalanceSnapshot | None:
        """Return the cached balance for a specific exchange/asset."""
        return self._balances.get((exchange, asset))

    def get_all_balances(self) -> dict[tuple[str, str], BalanceSnapshot]:
        """Return all cached balances."""
        return dict(self._balances)

    def get_exchange_balances(self, exchange: str) -> dict[str, BalanceSnapshot]:
        """Return all balances for a specific exchange."""
        return {
            asset: snap
            for (exch, asset), snap in self._balances.items()
            if exch == exchange
        }

    def get_asset_balances(self, asset: str) -> dict[str, BalanceSnapshot]:
        """Return balances for a specific asset across all exchanges."""
        return {
            exch: snap
            for (exch, a), snap in self._balances.items()
            if a == asset
        }

    def get_exchange_allocation(self) -> list[ExchangeAllocation]:
        """Compute allocation breakdown by exchange."""
        exchange_totals: dict[str, float] = {}
        exchange_assets: dict[str, dict[str, float]] = {}

        for (exchange, asset), snap in self._balances.items():
            exchange_totals[exchange] = exchange_totals.get(exchange, 0.0) + snap.usd_value
            if exchange not in exchange_assets:
                exchange_assets[exchange] = {}
            exchange_assets[exchange][asset] = snap.usd_value

        grand_total = sum(exchange_totals.values())

        allocations: list[ExchangeAllocation] = []
        for exchange, total_value in exchange_totals.items():
            allocations.append(ExchangeAllocation(
                exchange=exchange,
                total_value_usdt=total_value,
                pct_of_total=(total_value / grand_total * 100.0) if grand_total > 0 else 0.0,
                assets=exchange_assets.get(exchange, {}),
            ))

        allocations.sort(key=lambda a: a.total_value_usdt, reverse=True)
        return allocations

    def check_sufficient_balance(
        self, exchange: str, asset: str, amount: float
    ) -> bool:
        """Check whether there is sufficient free balance."""
        snap = self._balances.get((exchange, asset))
        if snap is None:
            return False
        return snap.free >= amount

    def get_total_value_usdt(self) -> float:
        """Get total portfolio value across all exchanges in USDT."""
        return sum(snap.usd_value for snap in self._balances.values())

    # ------------------------------------------------------------------
    # Imbalance detection
    # ------------------------------------------------------------------

    def detect_imbalance(
        self,
        asset: str,
        target_ratio: dict[str, float] | None = None,
    ) -> ImbalanceInfo:
        """Detect imbalance of *asset* across exchanges.

        If *target_ratio* is not provided, assumes equal distribution
        across all exchanges that hold the asset.
        """
        asset_balances = self.get_asset_balances(asset)
        if not asset_balances:
            return ImbalanceInfo(asset=asset)

        total = sum(snap.total for snap in asset_balances.values())
        if total <= 0:
            return ImbalanceInfo(asset=asset, total_amount=0.0)

        exchanges = list(asset_balances.keys())

        if target_ratio is None:
            # Equal distribution
            equal_pct = 1.0 / len(exchanges)
            target_ratio = {exch: equal_pct for exch in exchanges}

        actual_ratio: dict[str, float] = {}
        deviation: dict[str, float] = {}

        for exch, snap in asset_balances.items():
            actual = snap.total / total if total > 0 else 0.0
            target = target_ratio.get(exch, 0.0)
            actual_ratio[exch] = actual
            deviation[exch] = actual - target

        return ImbalanceInfo(
            asset=asset,
            target_ratio=target_ratio,
            actual_ratio=actual_ratio,
            deviation=deviation,
            total_amount=total,
        )

    def generate_rebalance_suggestions(
        self,
        threshold_pct: float = 10.0,
    ) -> list[RebalanceSuggestion]:
        """Generate suggestions for rebalancing assets across exchanges.

        Only suggests rebalances where the deviation exceeds *threshold_pct*.
        """
        suggestions: list[RebalanceSuggestion] = []

        # Find all unique assets
        assets: set[str] = set()
        for (_, asset) in self._balances:
            assets.add(asset)

        for asset in assets:
            imbalance = self.detect_imbalance(asset)
            if imbalance.total_amount <= 0:
                continue

            # Find exchanges that are over-allocated and under-allocated
            over: list[tuple[str, float]] = []
            under: list[tuple[str, float]] = []

            for exch, dev in imbalance.deviation.items():
                dev_pct = dev * 100.0
                if dev_pct > threshold_pct:
                    over.append((exch, dev))
                elif dev_pct < -threshold_pct:
                    under.append((exch, dev))

            # Match over -> under
            for over_exch, over_dev in over:
                for under_exch, under_dev in under:
                    # Transfer the smaller of the two imbalances
                    transfer_ratio = min(abs(over_dev), abs(under_dev))
                    transfer_qty = transfer_ratio * imbalance.total_amount

                    if transfer_qty > 0:
                        suggestions.append(RebalanceSuggestion(
                            asset=asset,
                            from_exchange=over_exch,
                            to_exchange=under_exch,
                            suggested_quantity=transfer_qty,
                            reason=(
                                f"{asset} is {over_dev * 100:.1f}% over-allocated on {over_exch} "
                                f"and {abs(under_dev) * 100:.1f}% under-allocated on {under_exch}"
                            ),
                        ))

        return suggestions

    # ------------------------------------------------------------------
    # Execution hooks
    # ------------------------------------------------------------------

    async def on_execution_completed(self, result: dict) -> None:
        """Hook called after an execution completes.

        Refreshes balances only for the exchanges involved in the trade
        and publishes a ``BALANCE_UPDATED`` event.

        Parameters
        ----------
        result:
            Execution result dict.  Expected keys include ``buy_exchange``
            and ``sell_exchange``.
        """
        buy_exchange: str | None = result.get("buy_exchange")
        sell_exchange: str | None = result.get("sell_exchange")

        exchanges_to_refresh: list[str] = []
        if buy_exchange:
            exchanges_to_refresh.append(buy_exchange)
        if sell_exchange and sell_exchange != buy_exchange:
            exchanges_to_refresh.append(sell_exchange)

        if not exchanges_to_refresh:
            logger.warning("on_execution_completed called but no exchanges found in result")
            return

        now = time.time()

        for exchange_name in exchanges_to_refresh:
            try:
                adapter = self._exchange_factory.get(exchange_name)
            except Exception:
                logger.warning("No adapter found for exchange {!r}, skipping refresh", exchange_name)
                continue

            try:
                balances = await adapter.get_balance()
            except Exception:
                logger.opt(exception=True).warning(
                    "Failed to fetch balance from {} after execution", exchange_name,
                )
                continue

            for asset, balance in balances.items():
                if balance.total <= 0:
                    # Remove stale entry if the balance dropped to zero
                    self._balances.pop((exchange_name, asset), None)
                    continue

                usd_value = self._estimate_usd_value(asset, balance.total)
                old_snap = self._balances.get((exchange_name, asset))

                snapshot = BalanceSnapshot(
                    exchange=exchange_name,
                    asset=asset,
                    free=balance.free,
                    locked=balance.locked,
                    total=balance.total,
                    usd_value=usd_value,
                    updated_at=now,
                )
                self._balances[(exchange_name, asset)] = snapshot

                # Log meaningful changes
                if old_snap is not None:
                    delta = snapshot.total - old_snap.total
                    if abs(delta) > 1e-12:
                        logger.info(
                            "Balance change on {}: {} {:+.8f} (was {:.8f}, now {:.8f})",
                            exchange_name, asset, delta, old_snap.total, snapshot.total,
                        )

                # Update Redis cache
                try:
                    await self._redis.set_json(
                        f"balance:{exchange_name}:{asset}",
                        {
                            "exchange": exchange_name,
                            "asset": asset,
                            "free": balance.free,
                            "locked": balance.locked,
                            "total": balance.total,
                            "usd_value": usd_value,
                            "ts": now,
                        },
                        ttl_s=120,
                    )
                except Exception:
                    logger.opt(exception=True).debug("Redis balance cache write failed")

        self._last_refresh = now

        await self._event_bus.publish(
            EventType.BALANCE_UPDATED,
            {
                "trigger": "execution_completed",
                "exchanges": exchanges_to_refresh,
                "total_assets": len(self._balances),
                "timestamp": now,
            },
        )

        logger.info(
            "Post-execution balance refresh complete for exchanges: {}",
            exchanges_to_refresh,
        )

    # ------------------------------------------------------------------
    # Exposure & summary
    # ------------------------------------------------------------------

    def get_exposure(self) -> dict:
        """Calculate current exposure across exchanges.

        Returns a dict with:
        - ``total_value_usdt``: aggregate portfolio value
        - ``per_exchange``: breakdown per exchange (value, pct, assets)
        - ``per_asset``: breakdown per asset (total amount, value, exchanges)
        - ``concentration_risk``: Herfindahl-Hirschman Index (0-1) across
          exchanges, where 1 means fully concentrated in one exchange.
        """
        total_value = self.get_total_value_usdt()

        # -- per exchange --------------------------------------------------
        per_exchange: dict[str, dict] = {}
        exchange_values: dict[str, float] = {}

        for (exchange, asset), snap in self._balances.items():
            if exchange not in per_exchange:
                per_exchange[exchange] = {
                    "value_usdt": 0.0,
                    "pct_of_total": 0.0,
                    "assets": {},
                }
            entry = per_exchange[exchange]
            entry["value_usdt"] += snap.usd_value
            entry["assets"][asset] = {
                "free": snap.free,
                "locked": snap.locked,
                "usd_value": snap.usd_value,
            }
            exchange_values[exchange] = exchange_values.get(exchange, 0.0) + snap.usd_value

        # Compute percentages
        for exchange, entry in per_exchange.items():
            entry["pct_of_total"] = (
                (entry["value_usdt"] / total_value * 100.0) if total_value > 0 else 0.0
            )

        # -- per asset -----------------------------------------------------
        per_asset: dict[str, dict] = {}

        for (exchange, asset), snap in self._balances.items():
            if asset not in per_asset:
                per_asset[asset] = {
                    "total_amount": 0.0,
                    "total_usd_value": 0.0,
                    "exchanges": [],
                }
            pa = per_asset[asset]
            pa["total_amount"] += snap.total
            pa["total_usd_value"] += snap.usd_value
            if exchange not in pa["exchanges"]:
                pa["exchanges"].append(exchange)

        # -- concentration risk (HHI) -------------------------------------
        concentration_risk = 0.0
        if total_value > 0:
            for value in exchange_values.values():
                share = value / total_value
                concentration_risk += share * share

        return {
            "total_value_usdt": total_value,
            "per_exchange": per_exchange,
            "per_asset": per_asset,
            "concentration_risk": concentration_risk,
        }

    def get_inventory_summary(self) -> dict:
        """Return a comprehensive inventory summary.

        Returns a dict with:
        - ``total_value_usdt``: aggregate portfolio value
        - ``exchange_count``: number of exchanges with balances
        - ``asset_count``: number of distinct assets held
        - ``last_refresh_at``: epoch timestamp of last refresh
        - ``allocations``: list of :class:`ExchangeAllocation` dicts
        - ``stablecoin_balance``: total USDT + USDC across all exchanges
        """
        exchanges: set[str] = set()
        assets: set[str] = set()
        stablecoin_balance = 0.0

        stablecoin_symbols = {"USDT", "USDC"}

        for (exchange, asset), snap in self._balances.items():
            exchanges.add(exchange)
            assets.add(asset)
            if asset in stablecoin_symbols:
                stablecoin_balance += snap.total

        allocations = self.get_exchange_allocation()

        return {
            "total_value_usdt": self.get_total_value_usdt(),
            "exchange_count": len(exchanges),
            "asset_count": len(assets),
            "last_refresh_at": self._last_refresh,
            "allocations": [
                {
                    "exchange": a.exchange,
                    "total_value_usdt": a.total_value_usdt,
                    "pct_of_total": a.pct_of_total,
                    "assets": a.assets,
                }
                for a in allocations
            ],
            "stablecoin_balance": stablecoin_balance,
        }
