"""
OrderTracker -- tracks live order lifecycle, polls for status updates,
handles partial fills, and runs reconciliation checks.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger

from app.core.config import Settings, settings
from app.core.events import EventBus, EventType
from app.exchanges.base import BaseExchangeAdapter, OrderStatus, StandardOrder
from app.exchanges.factory import ExchangeFactory


class OrderLifecycleState(StrEnum):
    """Internal tracking state for a live order."""
    PENDING_SUBMIT = "pending_submit"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"
    EXPIRED = "expired"


@dataclass
class TrackedOrder:
    """Full lifecycle record for a live order."""
    tracking_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    exchange: str = ""
    symbol: str = ""
    order_id: str = ""  # Exchange-assigned order ID
    client_order_id: str = ""
    side: str = ""  # "BUY" or "SELL"
    order_type: str = ""  # "LIMIT" or "MARKET"
    requested_quantity: float = 0.0
    requested_price: float | None = None
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None
    fee: float = 0.0
    fee_asset: str = ""
    state: OrderLifecycleState = OrderLifecycleState.PENDING_SUBMIT
    # Timestamps
    created_at: float = field(default_factory=time.time)
    submitted_at: float | None = None
    last_updated_at: float | None = None
    filled_at: float | None = None
    # Context
    execution_id: str = ""  # Links to the parent execution
    strategy_type: str = ""
    # Status history: list of (timestamp, old_state, new_state, details)
    history: list[dict[str, Any]] = field(default_factory=list)
    # Raw exchange responses
    submit_response: dict[str, Any] | None = None
    last_status_response: dict[str, Any] | None = None
    # Error info
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3

    @property
    def fill_pct(self) -> float:
        if self.requested_quantity <= 0:
            return 0.0
        return (self.filled_quantity / self.requested_quantity) * 100.0

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            OrderLifecycleState.FILLED,
            OrderLifecycleState.CANCELLED,
            OrderLifecycleState.FAILED,
            OrderLifecycleState.EXPIRED,
        )

    @property
    def notional_value(self) -> float:
        price = self.avg_fill_price or self.requested_price or 0.0
        return self.filled_quantity * price

    def record_transition(self, new_state: OrderLifecycleState, details: str = "") -> None:
        old = self.state
        self.history.append({
            "ts": time.time(),
            "from": old.value,
            "to": new_state.value,
            "details": details,
        })
        self.state = new_state
        self.last_updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracking_id": self.tracking_id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "side": self.side,
            "order_type": self.order_type,
            "requested_quantity": self.requested_quantity,
            "requested_price": self.requested_price,
            "filled_quantity": self.filled_quantity,
            "avg_fill_price": self.avg_fill_price,
            "fill_pct": self.fill_pct,
            "fee": self.fee,
            "fee_asset": self.fee_asset,
            "state": self.state.value,
            "notional_value": self.notional_value,
            "execution_id": self.execution_id,
            "strategy_type": self.strategy_type,
            "created_at": self.created_at,
            "submitted_at": self.submitted_at,
            "filled_at": self.filled_at,
            "last_updated_at": self.last_updated_at,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "history_count": len(self.history),
        }


@dataclass
class ReconciliationResult:
    """Result of comparing local tracking state vs exchange state."""
    order_tracking_id: str
    exchange: str
    symbol: str
    order_id: str
    local_state: str
    exchange_state: str
    local_filled_qty: float
    exchange_filled_qty: float
    qty_mismatch: float
    is_consistent: bool
    details: str = ""
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_tracking_id": self.order_tracking_id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "local_state": self.local_state,
            "exchange_state": self.exchange_state,
            "local_filled_qty": self.local_filled_qty,
            "exchange_filled_qty": self.exchange_filled_qty,
            "qty_mismatch": self.qty_mismatch,
            "is_consistent": self.is_consistent,
            "details": self.details,
            "checked_at": self.checked_at,
        }


@dataclass
class OrderTrackerMetrics:
    total_orders_tracked: int = 0
    active_orders: int = 0
    total_filled: int = 0
    total_partially_filled: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    total_reconciliation_runs: int = 0
    total_reconciliation_mismatches: int = 0
    last_reconciliation_at: float = 0.0


class OrderTracker:
    """Tracks live order lifecycle with polling-based status updates and reconciliation.

    Responsibilities:
    - Register orders when submitted
    - Poll exchange for status updates on active orders
    - Detect partial fills and publish events
    - Run periodic reconciliation to catch missed updates
    - Maintain full order lifecycle history
    """

    def __init__(
        self,
        event_bus: EventBus,
        exchange_factory: ExchangeFactory,
        config: Settings | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._exchange_factory = exchange_factory
        self._cfg = config or settings

        # Active orders being tracked: tracking_id -> TrackedOrder
        self._active_orders: dict[str, TrackedOrder] = {}
        # Completed orders (ring buffer, keep last N)
        self._completed_orders: list[TrackedOrder] = []
        self._max_completed: int = 500
        # Reconciliation results
        self._reconciliation_results: list[ReconciliationResult] = []
        self._max_reconciliation_results: int = 200

        self._metrics = OrderTrackerMetrics()

        # Polling config
        self._poll_interval_s: float = 2.0
        self._reconciliation_interval_s: float = 60.0

        # Background tasks
        self._poll_task: asyncio.Task | None = None
        self._reconciliation_task: asyncio.Task | None = None
        self._running = False

    @property
    def metrics(self) -> OrderTrackerMetrics:
        self._metrics.active_orders = len(self._active_orders)
        return self._metrics

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="order-tracker-poll"
        )
        self._reconciliation_task = asyncio.create_task(
            self._reconciliation_loop(), name="order-tracker-reconciliation"
        )
        logger.info("OrderTracker started (poll={}s, reconciliation={}s)",
                     self._poll_interval_s, self._reconciliation_interval_s)

    async def stop(self) -> None:
        self._running = False
        for task in [self._poll_task, self._reconciliation_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._poll_task = None
        self._reconciliation_task = None
        logger.info("OrderTracker stopped")

    # ------------------------------------------------------------------
    # Order registration
    # ------------------------------------------------------------------

    def register_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        execution_id: str = "",
        strategy_type: str = "",
    ) -> TrackedOrder:
        """Register a new order BEFORE submission. Returns a TrackedOrder in PENDING_SUBMIT state."""
        order = TrackedOrder(
            exchange=exchange,
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_quantity=quantity,
            requested_price=price,
            execution_id=execution_id,
            strategy_type=strategy_type,
        )
        self._active_orders[order.tracking_id] = order
        self._metrics.total_orders_tracked += 1
        logger.info("Order registered: tracking_id={} {}:{} {} {} qty={}",
                     order.tracking_id, exchange, symbol, side, order_type, quantity)
        return order

    def mark_submitted(
        self,
        tracking_id: str,
        order_id: str,
        client_order_id: str = "",
        raw_response: dict | None = None,
    ) -> None:
        """Mark an order as successfully submitted to the exchange."""
        order = self._active_orders.get(tracking_id)
        if not order:
            logger.warning("mark_submitted: tracking_id={} not found", tracking_id)
            return
        order.order_id = order_id
        order.client_order_id = client_order_id
        order.submitted_at = time.time()
        order.submit_response = raw_response
        order.record_transition(OrderLifecycleState.SUBMITTED, f"order_id={order_id}")
        logger.info("Order submitted: tracking_id={} order_id={}", tracking_id, order_id)

    def mark_failed(self, tracking_id: str, error: str) -> None:
        """Mark an order as failed (submission or execution failure)."""
        order = self._active_orders.get(tracking_id)
        if not order:
            return
        order.error_message = error
        order.record_transition(OrderLifecycleState.FAILED, error)
        self._metrics.total_failed += 1
        self._move_to_completed(tracking_id)
        logger.warning("Order failed: tracking_id={} error={}", tracking_id, error)

    # ------------------------------------------------------------------
    # Status update from exchange polling
    # ------------------------------------------------------------------

    async def _update_order_status(self, order: TrackedOrder) -> None:
        """Poll the exchange for the latest order status."""
        if not order.order_id:
            return

        adapter = self._exchange_factory.get(order.exchange)
        if not adapter:
            return

        try:
            status: StandardOrder = await adapter.get_order_status(
                order.symbol, order.order_id
            )
            order.last_status_response = status.raw
            order.last_updated_at = time.time()

            # Update fill info
            if status.filled_quantity > order.filled_quantity:
                old_filled = order.filled_quantity
                order.filled_quantity = status.filled_quantity
                order.avg_fill_price = status.avg_fill_price
                order.fee = status.fee or 0.0
                order.fee_asset = status.fee_asset or ""
                logger.info(
                    "Order fill update: tracking_id={} filled={}->{} avg_price={}",
                    order.tracking_id, old_filled, order.filled_quantity, order.avg_fill_price,
                )

            # State transitions based on exchange status
            if status.status == OrderStatus.FILLED and order.state != OrderLifecycleState.FILLED:
                order.filled_at = time.time()
                order.record_transition(OrderLifecycleState.FILLED, f"fill_pct={order.fill_pct:.1f}%")
                self._metrics.total_filled += 1
                self._move_to_completed(order.tracking_id)
                await self._event_bus.publish(EventType.LIVE_ORDER_FILLED, order.to_dict())

            elif status.status == OrderStatus.PARTIALLY_FILLED and order.state != OrderLifecycleState.PARTIALLY_FILLED:
                order.record_transition(
                    OrderLifecycleState.PARTIALLY_FILLED,
                    f"filled={order.filled_quantity}/{order.requested_quantity}",
                )
                self._metrics.total_partially_filled += 1

            elif status.status == OrderStatus.CANCELED and order.state != OrderLifecycleState.CANCELLED:
                order.record_transition(OrderLifecycleState.CANCELLED, "cancelled by exchange")
                self._metrics.total_cancelled += 1
                self._move_to_completed(order.tracking_id)

            elif status.status == OrderStatus.REJECTED and order.state != OrderLifecycleState.FAILED:
                order.record_transition(OrderLifecycleState.FAILED, "rejected by exchange")
                self._metrics.total_failed += 1
                self._move_to_completed(order.tracking_id)
                await self._event_bus.publish(EventType.LIVE_ORDER_FAILED, order.to_dict())

            elif status.status == OrderStatus.EXPIRED and order.state != OrderLifecycleState.EXPIRED:
                order.record_transition(OrderLifecycleState.EXPIRED, "expired")
                self._move_to_completed(order.tracking_id)

        except Exception:
            logger.opt(exception=True).warning(
                "Failed to poll status for tracking_id={} order_id={}",
                order.tracking_id, order.order_id,
            )
            order.retry_count += 1
            if order.retry_count >= order.max_retries:
                order.record_transition(
                    OrderLifecycleState.FAILED,
                    f"max retries ({order.max_retries}) exceeded during status poll",
                )
                self._metrics.total_failed += 1
                self._move_to_completed(order.tracking_id)

    def _move_to_completed(self, tracking_id: str) -> None:
        """Move order from active to completed ring buffer."""
        order = self._active_orders.pop(tracking_id, None)
        if order:
            self._completed_orders.append(order)
            if len(self._completed_orders) > self._max_completed:
                self._completed_orders = self._completed_orders[-self._max_completed:]

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Periodically poll exchange for active order status updates."""
        logger.info("Order status poll loop started")
        while self._running:
            try:
                # Snapshot active orders to avoid mutation during iteration
                active = list(self._active_orders.values())
                submitted = [o for o in active if o.state in (
                    OrderLifecycleState.SUBMITTED,
                    OrderLifecycleState.PARTIALLY_FILLED,
                )]
                if submitted:
                    tasks = [self._update_order_status(o) for o in submitted]
                    await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("Order poll loop error")
            await asyncio.sleep(self._poll_interval_s)

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    async def _reconciliation_loop(self) -> None:
        """Periodically reconcile local state with exchange state."""
        logger.info("Reconciliation loop started")
        while self._running:
            try:
                await asyncio.sleep(self._reconciliation_interval_s)
                await self.run_reconciliation()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).error("Reconciliation loop error")

    async def run_reconciliation(self) -> list[ReconciliationResult]:
        """Compare all recently completed orders against exchange state."""
        results: list[ReconciliationResult] = []
        self._metrics.total_reconciliation_runs += 1
        self._metrics.last_reconciliation_at = time.time()

        # Check recent completed orders (last 50)
        orders_to_check = self._completed_orders[-50:]

        for order in orders_to_check:
            if not order.order_id:
                continue
            adapter = self._exchange_factory.get(order.exchange)
            if not adapter:
                continue

            try:
                exchange_status = await adapter.get_order_status(
                    order.symbol, order.order_id
                )
                exchange_filled = exchange_status.filled_quantity or 0.0
                local_filled = order.filled_quantity

                qty_mismatch = abs(exchange_filled - local_filled)
                is_consistent = qty_mismatch < 1e-8

                # Check state consistency
                exchange_state_str = exchange_status.status.value if exchange_status.status else "unknown"

                if not is_consistent:
                    self._metrics.total_reconciliation_mismatches += 1
                    logger.warning(
                        "Reconciliation mismatch: tracking_id={} local_filled={} exchange_filled={} diff={}",
                        order.tracking_id, local_filled, exchange_filled, qty_mismatch,
                    )
                    await self._event_bus.publish(
                        EventType.RECONCILIATION_MISMATCH,
                        {
                            "tracking_id": order.tracking_id,
                            "exchange": order.exchange,
                            "symbol": order.symbol,
                            "order_id": order.order_id,
                            "local_filled": local_filled,
                            "exchange_filled": exchange_filled,
                            "mismatch": qty_mismatch,
                        },
                    )

                result = ReconciliationResult(
                    order_tracking_id=order.tracking_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    order_id=order.order_id,
                    local_state=order.state.value,
                    exchange_state=exchange_state_str,
                    local_filled_qty=local_filled,
                    exchange_filled_qty=exchange_filled,
                    qty_mismatch=qty_mismatch,
                    is_consistent=is_consistent,
                )
                results.append(result)

            except Exception:
                logger.opt(exception=True).debug(
                    "Reconciliation check failed for order_id={}", order.order_id
                )

        self._reconciliation_results.extend(results)
        if len(self._reconciliation_results) > self._max_reconciliation_results:
            self._reconciliation_results = self._reconciliation_results[-self._max_reconciliation_results:]

        logger.info(
            "Reconciliation complete: checked={} mismatches={}",
            len(results),
            sum(1 for r in results if not r.is_consistent),
        )
        return results

    # ------------------------------------------------------------------
    # Public getters
    # ------------------------------------------------------------------

    def get_active_orders(self) -> list[TrackedOrder]:
        return list(self._active_orders.values())

    def get_order(self, tracking_id: str) -> TrackedOrder | None:
        order = self._active_orders.get(tracking_id)
        if not order:
            for o in reversed(self._completed_orders):
                if o.tracking_id == tracking_id:
                    return o
        return order

    def get_orders_by_execution(self, execution_id: str) -> list[TrackedOrder]:
        all_orders = list(self._active_orders.values()) + self._completed_orders
        return [o for o in all_orders if o.execution_id == execution_id]

    def get_recent_completed(self, limit: int = 50) -> list[TrackedOrder]:
        return self._completed_orders[-limit:]

    def get_reconciliation_results(self, limit: int = 50) -> list[ReconciliationResult]:
        return self._reconciliation_results[-limit:]

    def get_mismatches(self) -> list[ReconciliationResult]:
        return [r for r in self._reconciliation_results if not r.is_consistent]
