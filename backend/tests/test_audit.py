"""Tests for the AuditService."""

from __future__ import annotations

import pytest

from app.services.audit import AuditEntry, AuditService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(max_entries: int = 10_000) -> AuditService:
    return AuditService(event_bus=None, max_entries=max_entries)


# ---------------------------------------------------------------------------
# Core logging
# ---------------------------------------------------------------------------

class TestLogEntry:
    def test_log_creates_entry(self):
        svc = _make_service()
        entry = svc.log("TEST_EVENT", "test_entity", "ent-1", "created", {"key": "val"})
        assert isinstance(entry, AuditEntry)
        assert entry.event_type == "TEST_EVENT"
        assert entry.entity_type == "test_entity"
        assert entry.entity_id == "ent-1"
        assert entry.action == "created"
        assert entry.details == {"key": "val"}
        assert svc.entry_count == 1

    def test_log_defaults_empty_details(self):
        svc = _make_service()
        entry = svc.log("E", "T", "id", "act")
        assert entry.details == {}

    def test_multiple_entries_accumulate(self):
        svc = _make_service()
        for i in range(5):
            svc.log("E", "T", f"id-{i}", "act")
        assert svc.entry_count == 5


# ---------------------------------------------------------------------------
# Ring buffer
# ---------------------------------------------------------------------------

class TestRingBuffer:
    def test_trims_to_max_entries(self):
        svc = _make_service(max_entries=5)
        for i in range(10):
            svc.log("E", "T", f"id-{i}", "act")
        assert svc.entry_count == 5

    def test_oldest_entries_discarded(self):
        svc = _make_service(max_entries=3)
        for i in range(5):
            svc.log("E", "T", f"id-{i}", "act")
        entries = svc.get_entries(limit=10)
        # Newest first, so ids should be 4, 3, 2
        ids = [e.entity_id for e in entries]
        assert ids == ["id-4", "id-3", "id-2"]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

class TestGetEntries:
    def test_filter_by_entity_type(self):
        svc = _make_service()
        svc.log("E", "execution", "ex-1", "created")
        svc.log("E", "alert", "al-1", "created")
        svc.log("E", "execution", "ex-2", "updated")

        results = svc.get_entries(entity_type="execution")
        assert len(results) == 2
        assert all(e.entity_type == "execution" for e in results)

    def test_filter_by_event_type(self):
        svc = _make_service()
        svc.log("RISK_CHECK", "execution", "ex-1", "approved")
        svc.log("STATE_TRANSITION", "execution", "ex-1", "state_changed")

        results = svc.get_entries(event_type="RISK_CHECK")
        assert len(results) == 1
        assert results[0].event_type == "RISK_CHECK"

    def test_filter_by_entity_id(self):
        svc = _make_service()
        svc.log("E", "T", "target-id", "act")
        svc.log("E", "T", "other-id", "act")

        results = svc.get_entries(entity_id="target-id")
        assert len(results) == 1

    def test_limit_and_offset(self):
        svc = _make_service()
        for i in range(10):
            svc.log("E", "T", f"id-{i}", "act")

        results = svc.get_entries(limit=3, offset=2)
        assert len(results) == 3

    def test_newest_first_ordering(self):
        svc = _make_service()
        svc.log("E", "T", "first", "act")
        svc.log("E", "T", "second", "act")
        results = svc.get_entries()
        assert results[0].entity_id == "second"
        assert results[1].entity_id == "first"


class TestGetEntriesForExecution:
    def test_matches_execution_id(self):
        svc = _make_service()
        svc.log("EXEC_CREATED", "execution", "exec-abc", "created")
        svc.log("LEG_SUBMITTED", "leg", "exec-abc:leg0", "submitted",
                {"execution_id": "exec-abc"})
        svc.log("UNRELATED", "execution", "exec-xyz", "created")

        results = svc.get_entries_for_execution("exec-abc")
        assert len(results) == 2

    def test_matches_details_execution_id(self):
        svc = _make_service()
        svc.log("PNL", "pnl", "pnl-1", "recorded", {"execution_id": "exec-abc"})
        results = svc.get_entries_for_execution("exec-abc")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------

class TestConvenienceMethods:
    def test_log_execution_created(self):
        svc = _make_service()
        entry = svc.log_execution_created("ex-1", {"plan_id": "p1", "strategy_type": "CROSS_EXCHANGE"})
        assert entry.event_type == "EXECUTION_CREATED"
        assert entry.entity_id == "ex-1"

    def test_log_risk_check_approved(self):
        svc = _make_service()
        entry = svc.log_risk_check("ex-1", {"approved": True, "violations": [], "rule_count": 5})
        assert entry.action == "approved"

    def test_log_risk_check_rejected(self):
        svc = _make_service()
        entry = svc.log_risk_check("ex-1", {"approved": False, "violations": ["rule_a"]})
        assert entry.action == "rejected"

    def test_log_state_transition(self):
        svc = _make_service()
        entry = svc.log_state_transition("execution", "ex-1", "CREATED", "EXECUTING")
        assert entry.event_type == "STATE_TRANSITION"
        assert entry.details["from_state"] == "CREATED"

    def test_log_leg_filled(self):
        svc = _make_service()
        entry = svc.log_leg_filled("ex-1", 0, 60000.0, 0.1)
        assert entry.event_type == "LEG_FILLED"
        assert entry.details["notional_usdt"] == pytest.approx(6000.0)

    def test_log_alert_generated(self):
        svc = _make_service()
        entry = svc.log_alert_generated("alert-1", "EXECUTION_FAILED", "WARNING", "msg")
        assert entry.event_type == "ALERT_GENERATED"

    def test_log_inventory_update(self):
        svc = _make_service()
        entry = svc.log_inventory_update("binance", "BTC", 1.0, 1.1)
        assert entry.details["delta"] == pytest.approx(0.1)

    def test_clear(self):
        svc = _make_service()
        svc.log("E", "T", "id", "act")
        removed = svc.clear()
        assert removed == 1
        assert svc.entry_count == 0
