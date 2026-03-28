"""
Execution plan endpoints -- list, detail, active, and manual trigger.

Router prefix: /api/executions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.execution import ExecutionPlan, ExecutionPlanStatus
from app.models.opportunity import ArbitrageOpportunity, OpportunityStatus
from app.schemas.common import StatusResponse
from app.schemas.execution import (
    ExecutionCreate,
    ExecutionListResponse,
    ExecutionPlanSchema,
)


# ---------------------------------------------------------------------------
# Request bodies for coordinator-backed endpoints
# ---------------------------------------------------------------------------

class ExecuteOpportunityRequest(BaseModel):
    opportunity_id: str = Field(..., description="ID of a recently detected opportunity")
    mode: str = Field(default="PAPER", description="Execution mode: PAPER or LIVE")


class CrossExchangeRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair, e.g. BTC/USDT")
    buy_exchange: str = Field(..., description="Exchange to buy on")
    sell_exchange: str = Field(..., description="Exchange to sell on")
    quantity: float = Field(..., gt=0, description="Quantity to trade")
    mode: str = Field(default="PAPER", description="Execution mode: PAPER or LIVE")


class TriangularRequest(BaseModel):
    exchange: str = Field(..., description="Exchange to trade on")
    path: list[str] = Field(..., min_length=3, max_length=3, description="List of 3 symbols forming the triangular path")
    start_amount: float = Field(default=1000.0, gt=0, description="Starting notional in quote asset")
    mode: str = Field(default="PAPER", description="Execution mode: PAPER or LIVE")

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get(
    "/active",
    response_model=list[ExecutionPlanSchema],
    summary="Get currently active executions",
)
async def get_active_executions(
    db: AsyncSession = Depends(get_db),
) -> list[ExecutionPlanSchema]:
    """Return all executions currently in an active (non-terminal) state."""

    active_statuses = [
        ExecutionPlanStatus.PENDING,
        ExecutionPlanStatus.SUBMITTING,
        ExecutionPlanStatus.PARTIAL_FILLED,
        ExecutionPlanStatus.HEDGING,
    ]
    try:
        result = await db.execute(
            select(ExecutionPlan)
            .where(ExecutionPlan.status.in_(active_statuses))
            .order_by(ExecutionPlan.started_at.desc())
        )
        plans = result.scalars().all()
        return [ExecutionPlanSchema.model_validate(p) for p in plans]
    except Exception as exc:
        logger.debug("Failed to query active executions: {}", exc)
        return []


@router.get(
    "/",
    response_model=ExecutionListResponse,
    summary="List executions with filters",
)
async def list_executions(
    status: Optional[str] = Query(None, description="Filter by plan status"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_time: Optional[datetime] = Query(None, description="Filter by start time (ISO8601)"),
    end_time: Optional[datetime] = Query(None, description="Filter by end time (ISO8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> ExecutionListResponse:
    """Return a paginated list of execution plans with optional filters."""

    try:
        query = select(ExecutionPlan)
        count_query = select(func.count()).select_from(ExecutionPlan)

        if status:
            query = query.where(ExecutionPlan.status == status)
            count_query = count_query.where(ExecutionPlan.status == status)
        if strategy_type:
            query = query.where(ExecutionPlan.strategy_type == strategy_type)
            count_query = count_query.where(ExecutionPlan.strategy_type == strategy_type)
        if start_time:
            query = query.where(ExecutionPlan.started_at >= start_time)
            count_query = count_query.where(ExecutionPlan.started_at >= start_time)
        if end_time:
            query = query.where(ExecutionPlan.started_at <= end_time)
            count_query = count_query.where(ExecutionPlan.started_at <= end_time)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(ExecutionPlan.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        plans = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return ExecutionListResponse(
            items=[ExecutionPlanSchema.model_validate(p) for p in plans],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except Exception as exc:
        logger.debug("Failed to query executions: {}", exc)
        return ExecutionListResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )


@router.get(
    "/{execution_id}",
    response_model=ExecutionPlanSchema,
    summary="Get execution with legs detail",
)
async def get_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExecutionPlanSchema:
    """Return a single execution plan including all its legs."""

    result = await db.execute(
        select(ExecutionPlan).where(ExecutionPlan.id == execution_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return ExecutionPlanSchema.model_validate(plan)


@router.post(
    "/",
    response_model=ExecutionPlanSchema,
    status_code=201,
    summary="Manually trigger execution",
)
async def create_execution(
    payload: ExecutionCreate,
    db: AsyncSession = Depends(get_db),
) -> ExecutionPlanSchema:
    """Manually trigger execution of an arbitrage opportunity.

    The opportunity must exist and be in a DETECTED state.
    """

    # Validate opportunity exists
    opp_result = await db.execute(
        select(ArbitrageOpportunity).where(ArbitrageOpportunity.id == payload.opportunity_id)
    )
    opportunity = opp_result.scalar_one_or_none()
    if opportunity is None:
        raise HTTPException(status_code=404, detail=f"Opportunity {payload.opportunity_id} not found")

    if opportunity.status != OpportunityStatus.DETECTED:
        raise HTTPException(
            status_code=400,
            detail=f"Opportunity is in {opportunity.status.value} state; only DETECTED opportunities can be executed",
        )

    if not opportunity.is_executable:
        raise HTTPException(
            status_code=400,
            detail=f"Opportunity is not executable: {opportunity.rejection_reason or 'unknown reason'}",
        )

    # Create execution plan
    plan = ExecutionPlan(
        opportunity_id=opportunity.id,
        strategy_type=opportunity.strategy_type,
        mode=payload.mode,
        target_quantity=float(payload.target_quantity) if payload.target_quantity else None,
        target_value_usdt=float(payload.target_value_usdt) if payload.target_value_usdt else None,
        planned_profit_pct=float(opportunity.estimated_net_profit_pct) if opportunity.estimated_net_profit_pct else None,
        status=ExecutionPlanStatus.PENDING,
        started_at=datetime.now(timezone.utc),
    )

    # Mark opportunity as executing
    opportunity.status = OpportunityStatus.EXECUTING

    db.add(plan)
    await db.flush()
    await db.refresh(plan)

    logger.info(
        "Manual execution triggered: plan={}, opportunity={}, mode={}",
        plan.id,
        opportunity.id,
        payload.mode,
    )

    return ExecutionPlanSchema.model_validate(plan)


# ---------------------------------------------------------------------------
# Coordinator-backed endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/execute-opportunity",
    summary="Execute a detected opportunity through the coordinator",
)
async def execute_opportunity(
    payload: ExecuteOpportunityRequest,
    request: Request,
):
    """Find a recently detected opportunity by ID and execute it via the
    ExecutionCoordinator."""

    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ExecutionCoordinator not available")

    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(status_code=503, detail="ArbitrageScanner not available")

    # Search recent opportunities from the scanner
    opportunity = None
    for opp in scanner.recent_opportunities:
        if opp.id == payload.opportunity_id:
            opportunity = opp
            break

    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity {payload.opportunity_id} not found in recent opportunities",
        )

    result = await coordinator.execute_opportunity(opportunity, mode=payload.mode)
    return {
        "execution_id": result.execution_id,
        "state": result.state,
        "mode": result.mode,
        "strategy_type": result.strategy_type,
        "opportunity_id": result.opportunity_id,
        "actual_profit_usdt": result.actual_profit_usdt,
        "error_message": result.error_message,
    }


@router.post(
    "/cross-exchange",
    summary="Direct cross-exchange execution",
)
async def execute_cross_exchange(
    payload: CrossExchangeRequest,
    request: Request,
):
    """Execute a cross-exchange arbitrage directly via the coordinator."""

    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ExecutionCoordinator not available")

    result = await coordinator.execute_cross_exchange(
        symbol=payload.symbol,
        buy_exchange=payload.buy_exchange,
        sell_exchange=payload.sell_exchange,
        quantity=payload.quantity,
        mode=payload.mode,
    )
    return result.to_dict()


@router.post(
    "/triangular",
    summary="Direct triangular execution",
)
async def execute_triangular(
    payload: TriangularRequest,
    request: Request,
):
    """Execute a triangular arbitrage directly via the coordinator."""

    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ExecutionCoordinator not available")

    result = await coordinator.execute_triangular(
        exchange=payload.exchange,
        path=payload.path,
        start_amount=payload.start_amount,
        mode=payload.mode,
    )
    return result.to_dict()


@router.get(
    "/active-detail",
    summary="Get all active executions with full detail",
)
async def get_active_executions_detail(
    request: Request,
):
    """Return all currently in-flight executions from the coordinator."""

    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ExecutionCoordinator not available")

    return await coordinator.get_active_executions()


@router.get(
    "/{execution_id}/detail",
    summary="Get execution detail with audit trail",
)
async def get_execution_detail(
    execution_id: str,
    request: Request,
):
    """Return detailed information about an execution including its audit trail."""

    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ExecutionCoordinator not available")

    detail = await coordinator.get_execution_detail(execution_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found in coordinator (may have completed and been cleaned up)",
        )
    return detail
