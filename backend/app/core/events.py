"""
Lightweight async event bus for internal pub/sub.

Usage::

    from app.core.events import event_bus, EventType

    # Subscribe
    async def on_opportunity(data: dict):
        ...

    event_bus.subscribe(EventType.OPPORTUNITY_FOUND, on_opportunity)

    # Publish
    await event_bus.publish(EventType.OPPORTUNITY_FOUND, {"symbol": "BTC/USDT", ...})
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any, Callable, Coroutine

from loguru import logger

# Type alias for subscriber callbacks.
Callback = Callable[..., Coroutine[Any, Any, None]]


class EventType(StrEnum):
    """All event types flowing through the bus."""

    MARKET_UPDATE = auto()
    OPPORTUNITY_FOUND = auto()
    OPPORTUNITY_EXPIRED = auto()
    EXECUTION_STARTED = auto()
    EXECUTION_COMPLETED = auto()
    EXECUTION_FAILED = auto()
    RISK_VIOLATION = auto()
    ALERT_TRIGGERED = auto()
    BALANCE_UPDATED = auto()
    SYSTEM_EVENT = auto()
    KILL_SWITCH_ACTIVATED = auto()
    KILL_SWITCH_RELEASED = auto()
    CIRCUIT_BREAKER_OPENED = auto()
    CIRCUIT_BREAKER_RESET = auto()
    LIVE_ORDER_SUBMITTED = auto()
    LIVE_ORDER_FILLED = auto()
    LIVE_ORDER_FAILED = auto()
    LIVE_MODE_CHANGED = auto()
    CREDENTIAL_VALIDATED = auto()
    RECONCILIATION_MISMATCH = auto()


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable envelope for every published event."""

    type: EventType
    data: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@dataclass
class _Subscription:
    callback: Callback
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


class EventBus:
    """Async in-process event bus.

    * Subscribers are invoked concurrently via ``asyncio.gather``.
    * A failing subscriber never prevents other subscribers from running.
    * ``publish`` is fire-and-forget by default; use ``publish_and_wait``
      if you need to block until all handlers finish.
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[_Subscription]] = {et: [] for et in EventType}
        self._lock = asyncio.Lock()
        self._history_size = 1000
        self._recent_events: list[Event] = []

    # -- subscribe / unsubscribe --------------------------------------------

    def subscribe(self, event_type: EventType, callback: Callback) -> str:
        """Register *callback* for *event_type*.  Returns a subscription id
        that can be passed to :meth:`unsubscribe`."""
        sub = _Subscription(callback=callback)
        self._subscribers[event_type].append(sub)
        logger.debug("Subscribed {cb} to {et} (sub_id={sid})", cb=callback.__qualname__, et=event_type, sid=sub.id)
        return sub.id

    def unsubscribe(self, event_type: EventType, subscription_id: str) -> bool:
        """Remove a subscription.  Returns ``True`` if found and removed."""
        subs = self._subscribers[event_type]
        for idx, sub in enumerate(subs):
            if sub.id == subscription_id:
                subs.pop(idx)
                logger.debug("Unsubscribed {sid} from {et}", sid=subscription_id, et=event_type)
                return True
        return False

    def unsubscribe_all(self, event_type: EventType | None = None) -> int:
        """Remove all subscribers, optionally filtered by *event_type*.
        Returns the number removed."""
        count = 0
        types = [event_type] if event_type else list(EventType)
        for et in types:
            count += len(self._subscribers[et])
            self._subscribers[et].clear()
        return count

    # -- publish ------------------------------------------------------------

    async def publish(self, event_type: EventType, data: dict[str, Any] | None = None) -> Event:
        """Create an :class:`Event`, dispatch to all subscribers concurrently,
        and return the event.  Exceptions in subscribers are logged but do not
        propagate."""
        event = Event(type=event_type, data=data or {})
        self._record(event)

        subs = self._subscribers.get(event_type, [])
        if not subs:
            return event

        tasks = [self._safe_invoke(sub.callback, event) for sub in subs]
        await asyncio.gather(*tasks)
        return event

    async def publish_and_wait(self, event_type: EventType, data: dict[str, Any] | None = None) -> Event:
        """Same as :meth:`publish` but guaranteed to await all handlers."""
        return await self.publish(event_type, data)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    async def _safe_invoke(callback: Callback, event: Event) -> None:
        try:
            await callback(event)
        except Exception:
            logger.opt(exception=True).error(
                "Subscriber {cb} raised for event {et}",
                cb=callback.__qualname__,
                et=event.type,
            )

    def _record(self, event: Event) -> None:
        self._recent_events.append(event)
        if len(self._recent_events) > self._history_size:
            self._recent_events = self._recent_events[-self._history_size :]

    def recent_events(self, event_type: EventType | None = None, limit: int = 50) -> list[Event]:
        """Return the most recent events, optionally filtered by type."""
        events = self._recent_events
        if event_type is not None:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]

    @property
    def subscriber_counts(self) -> dict[str, int]:
        return {et.value: len(subs) for et, subs in self._subscribers.items()}


# Module-level singleton.
event_bus = EventBus()
