"""
Audit trail endpoints -- list, filter, and inspect audit entries.

Router prefix: /api/audit
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from loguru import logger

from app.services.audit import AuditService

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _get_audit_service(request: Request) -> AuditService:
    """Retrieve AuditService from app state, or create a fallback in-memory instance."""
    svc = getattr(request.app.state, "audit_service", None)
    if svc is None:
        logger.warning("AuditService not found on app.state -- using ephemeral instance")
        svc = AuditService()
        request.app.state.audit_service = svc
    return svc


@router.get(
    "/",
    summary="List audit entries with filters",
)
async def list_audit_entries(
    request: Request,
    entity_type: Optional[str] = Query(None, description="Filter by entity type (execution, alert, leg, inventory, ...)"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type (EXECUTION_CREATED, RISK_CHECK, ...)"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
) -> dict[str, Any]:
    """Return audit entries with optional filtering, newest first."""
    audit = _get_audit_service(request)
    entries = audit.get_entries(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [e.to_dict() for e in entries],
        "total": audit.entry_count,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/execution/{execution_id}",
    summary="Get audit trail for a specific execution",
)
async def get_execution_audit(
    execution_id: str,
    request: Request,
) -> dict[str, Any]:
    """Return all audit entries related to a specific execution ID."""
    audit = _get_audit_service(request)
    entries = audit.get_entries_for_execution(execution_id)
    return {
        "execution_id": execution_id,
        "items": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.get(
    "/stats",
    summary="Get audit entry counts by event type",
)
async def get_audit_stats(
    request: Request,
) -> dict[str, Any]:
    """Return aggregate counts of audit entries grouped by event type."""
    audit = _get_audit_service(request)
    all_entries = audit.get_entries(limit=audit.entry_count)
    counts: Counter[str] = Counter(e.event_type for e in all_entries)
    return {
        "total_entries": audit.entry_count,
        "by_event_type": dict(counts),
    }
