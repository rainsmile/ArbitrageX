"""Structured audit logging for all system events.

Provides a centralised, queryable audit trail for executions, risk checks,
state transitions, order fills, alerts, and inventory changes.  Entries are
kept in an in-memory ring buffer and optionally published to the event bus.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.events import EventBus, EventType


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AuditEntry:
    """A single audit record."""
    id: str
    event_type: str   # OPPORTUNITY_DETECTED, EXECUTION_CREATED, RISK_CHECK, ...
    entity_type: str  # execution, opportunity, order, alert, leg, inventory
    entity_id: str
    action: str       # created, updated, state_changed, rejected, filled, ...
    details: dict[str, Any]
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------

class AuditService:
    """Records structured audit entries for compliance and debugging.

    Maintains an in-memory ring buffer of up to *max_entries* items and
    optionally publishes each entry to the :class:`EventBus`.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        max_entries: int = 10_000,
    ) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Core logging
    # ------------------------------------------------------------------

    def log(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Create and store an audit entry.  Returns the entry."""
        entry = AuditEntry(
            id=uuid.uuid4().hex,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details=details or {},
            timestamp=datetime.now(timezone.utc),
        )
        self._entries.append(entry)

        # Trim if over capacity
        if len(self._entries) > self._max_entries:
            overflow = len(self._entries) - self._max_entries
            self._entries = self._entries[overflow:]

        logger.debug(
            "[AUDIT] {} {} {} :: {} | {}",
            event_type, entity_type, entity_id, action,
            details or "",
        )

        # Publish to event bus (fire-and-forget style; caller can await separately)
        if self._event_bus is not None:
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(
                        EventType.SYSTEM_EVENT,
                        {"audit": entry.to_dict()},
                    )
                )
            except RuntimeError:
                # No running event loop -- skip async publish
                pass

        return entry

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def log_execution_created(
        self,
        execution_id: str,
        plan_data: dict[str, Any],
    ) -> AuditEntry:
        """Record that an execution plan was created."""
        return self.log(
            event_type="EXECUTION_CREATED",
            entity_type="execution",
            entity_id=execution_id,
            action="created",
            details={
                "plan_id": plan_data.get("plan_id", ""),
                "strategy_type": plan_data.get("strategy_type", ""),
                "mode": plan_data.get("mode", ""),
                "target_quantity": plan_data.get("target_quantity", 0),
                "target_notional_usdt": plan_data.get("target_notional_usdt", 0),
                "planned_net_profit": plan_data.get("planned_net_profit", 0),
                "leg_count": plan_data.get("leg_count", 0),
            },
        )

    def log_risk_check(
        self,
        execution_id: str,
        result: dict[str, Any],
    ) -> AuditEntry:
        """Record the outcome of a risk check."""
        return self.log(
            event_type="RISK_CHECK",
            entity_type="execution",
            entity_id=execution_id,
            action="approved" if result.get("approved") else "rejected",
            details={
                "approved": result.get("approved", False),
                "violations": result.get("violations", []),
                "rule_count": result.get("rule_count", 0),
            },
        )

    def log_state_transition(
        self,
        entity_type: str,
        entity_id: str,
        from_state: str,
        to_state: str,
        reason: str = "",
    ) -> AuditEntry:
        """Record a state machine transition."""
        return self.log(
            event_type="STATE_TRANSITION",
            entity_type=entity_type,
            entity_id=entity_id,
            action="state_changed",
            details={
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
            },
        )

    def log_leg_submitted(
        self,
        execution_id: str,
        leg_index: int,
        exchange: str,
        symbol: str,
        side: str,
    ) -> AuditEntry:
        """Record that an execution leg was submitted to an exchange."""
        return self.log(
            event_type="LEG_SUBMITTED",
            entity_type="leg",
            entity_id=f"{execution_id}:leg{leg_index}",
            action="submitted",
            details={
                "execution_id": execution_id,
                "leg_index": leg_index,
                "exchange": exchange,
                "symbol": symbol,
                "side": side,
            },
        )

    def log_leg_filled(
        self,
        execution_id: str,
        leg_index: int,
        fill_price: float,
        fill_qty: float,
    ) -> AuditEntry:
        """Record that an execution leg was filled."""
        return self.log(
            event_type="LEG_FILLED",
            entity_type="leg",
            entity_id=f"{execution_id}:leg{leg_index}",
            action="filled",
            details={
                "execution_id": execution_id,
                "leg_index": leg_index,
                "fill_price": fill_price,
                "fill_qty": fill_qty,
                "notional_usdt": fill_price * fill_qty,
            },
        )

    def log_alert_generated(
        self,
        alert_id: str,
        alert_type: str,
        severity: str,
        message: str,
    ) -> AuditEntry:
        """Record that an alert was generated."""
        return self.log(
            event_type="ALERT_GENERATED",
            entity_type="alert",
            entity_id=alert_id,
            action="created",
            details={
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
            },
        )

    def log_inventory_update(
        self,
        exchange: str,
        asset: str,
        old_balance: float,
        new_balance: float,
    ) -> AuditEntry:
        """Record a balance change on an exchange."""
        delta = new_balance - old_balance
        return self.log(
            event_type="INVENTORY_UPDATE",
            entity_type="inventory",
            entity_id=f"{exchange}:{asset}",
            action="updated",
            details={
                "exchange": exchange,
                "asset": asset,
                "old_balance": old_balance,
                "new_balance": new_balance,
                "delta": delta,
            },
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_entries(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Return audit entries with optional filtering.

        Results are returned in reverse-chronological order (newest first).
        """
        filtered = self._entries

        if entity_type is not None:
            filtered = [e for e in filtered if e.entity_type == entity_type]
        if entity_id is not None:
            filtered = [e for e in filtered if e.entity_id == entity_id]
        if event_type is not None:
            filtered = [e for e in filtered if e.event_type == event_type]

        # Reverse for newest-first ordering, then apply offset/limit
        filtered = list(reversed(filtered))
        return filtered[offset : offset + limit]

    def get_entries_for_execution(self, execution_id: str) -> list[AuditEntry]:
        """Return all audit entries related to a specific execution.

        Matches entries where:
        - entity_id equals the execution_id, OR
        - entity_id starts with the execution_id (for leg entries like
          ``{execution_id}:leg0``), OR
        - the details dict contains the execution_id.
        """
        results: list[AuditEntry] = []
        for entry in self._entries:
            if entry.entity_id == execution_id:
                results.append(entry)
            elif entry.entity_id.startswith(f"{execution_id}:"):
                results.append(entry)
            elif entry.details.get("execution_id") == execution_id:
                results.append(entry)
        return results

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def clear(self) -> int:
        """Remove all entries.  Returns the number removed."""
        count = len(self._entries)
        self._entries.clear()
        return count
