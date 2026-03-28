"""
Alert endpoints -- list, read, resolve.

Router prefix: /api/alerts
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.alert import Alert, AlertSeverity
from app.schemas.alert import AlertListResponse, AlertSchema
from app.schemas.common import StatusResponse

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get(
    "/active",
    response_model=list[AlertSchema],
    summary="Get active unresolved alerts",
)
async def get_active_alerts(
    db: AsyncSession = Depends(get_db),
) -> list[AlertSchema]:
    """Return all unresolved, active alerts ordered by most recent."""

    try:
        result = await db.execute(
            select(Alert)
            .where(Alert.is_resolved == False)  # noqa: E712
            .order_by(Alert.created_at.desc())
            .limit(100)
        )
        alerts = result.scalars().all()
        return [AlertSchema.model_validate(a) for a in alerts]
    except Exception as exc:
        logger.debug("Failed to query active alerts: {}", exc)
        return []


@router.get(
    "/",
    response_model=AlertListResponse,
    summary="List alerts with filters",
)
async def list_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity (INFO, WARNING, CRITICAL)"),
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    is_resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    start_time: Optional[datetime] = Query(None, description="Start of time range (ISO8601)"),
    end_time: Optional[datetime] = Query(None, description="End of time range (ISO8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """Return a paginated list of alerts with optional filters."""

    try:
        query = select(Alert)
        count_query = select(func.count()).select_from(Alert)

        if severity:
            query = query.where(Alert.severity == severity)
            count_query = count_query.where(Alert.severity == severity)
        if is_read is not None:
            query = query.where(Alert.is_read == is_read)
            count_query = count_query.where(Alert.is_read == is_read)
        if is_resolved is not None:
            query = query.where(Alert.is_resolved == is_resolved)
            count_query = count_query.where(Alert.is_resolved == is_resolved)
        if start_time:
            query = query.where(Alert.created_at >= start_time)
            count_query = count_query.where(Alert.created_at >= start_time)
        if end_time:
            query = query.where(Alert.created_at <= end_time)
            count_query = count_query.where(Alert.created_at <= end_time)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Alert.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        alerts = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return AlertListResponse(
            items=[AlertSchema.model_validate(a) for a in alerts],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except Exception as exc:
        logger.debug("Failed to query alerts: {}", exc)
        return AlertListResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )


@router.get(
    "/{alert_id}",
    response_model=AlertSchema,
    summary="Get a specific alert",
)
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AlertSchema:
    """Return a single alert by its ID."""

    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return AlertSchema.model_validate(alert)


@router.post(
    "/{alert_id}/read",
    response_model=AlertSchema,
    summary="Mark alert as read",
)
async def mark_alert_read(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AlertSchema:
    """Mark an alert as read."""

    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.is_read = True
    await db.flush()
    await db.refresh(alert)
    return AlertSchema.model_validate(alert)


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertSchema,
    summary="Mark alert as resolved",
)
async def resolve_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AlertSchema:
    """Mark an alert as resolved."""

    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    alert.is_read = True  # Also mark as read when resolved
    await db.flush()
    await db.refresh(alert)
    return AlertSchema.model_validate(alert)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=StatusResponse,
    summary="Acknowledge an alert",
)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    """Mark an alert as acknowledged (read) without resolving it."""

    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.is_read = True
    await db.flush()
    await db.refresh(alert)

    # Log audit entry if audit_service is available
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is not None:
        audit_service.log(
            event_type="ALERT_ACKNOWLEDGED",
            entity_type="alert",
            entity_id=str(alert_id),
            action="acknowledged",
            details={"alert_type": alert.alert_type, "title": alert.title},
        )

    return StatusResponse(status="ok", message=f"Alert {alert_id} acknowledged")
