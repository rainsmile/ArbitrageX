"""
System health, metrics, exchange status, and WebSocket status endpoints.

Router prefix: /api/system
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, get_redis
from app.db.redis import RedisClient
from app.models.exchange import Exchange
from app.models.execution import ExecutionPlan, ExecutionPlanStatus
from app.models.strategy import StrategyConfig
from app.schemas.exchange import ExchangeStatus
from app.schemas.system import SystemHealth, SystemMetrics, WsStatus

router = APIRouter(prefix="/api/system", tags=["system"])

# Track process start time for uptime calculation
_START_TIME = time.time()


@router.get(
    "/health",
    response_model=SystemHealth,
    summary="System health check",
)
async def health_check(request: Request) -> SystemHealth:
    """Return overall system health including database, Redis, and exchange
    connectivity status."""

    # -- Database --
    db_status = "disconnected"
    try:
        async with request.app.state.redis:  # type: ignore[union-attr]
            pass
    except Exception:
        pass

    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        db_status = "disconnected"

    # -- Redis --
    redis_status = "disconnected"
    redis_client: Optional[RedisClient] = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        try:
            await redis_client.client.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "disconnected"

    # -- Exchanges --
    exchange_statuses: dict[str, str] = {}
    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            result = await session.execute(select(Exchange))
            exchanges = result.scalars().all()
            for ex in exchanges:
                exchange_statuses[ex.name] = ex.api_status
    except Exception:
        # Fallback demo data
        for name in settings.trading.enabled_exchanges:
            exchange_statuses[name] = "UNKNOWN"

    uptime = int(time.time() - _START_TIME)
    overall = "healthy"
    if db_status != "connected" or redis_status != "connected":
        overall = "degraded"
    if db_status != "connected" and redis_status != "connected":
        overall = "unhealthy"

    return SystemHealth(
        status=overall,
        database=db_status,
        redis=redis_status,
        exchanges=exchange_statuses,
        uptime_seconds=uptime,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/metrics",
    response_model=SystemMetrics,
    summary="System operational metrics",
)
async def system_metrics(request: Request) -> SystemMetrics:
    """Return a snapshot of operational metrics including scan rate, execution
    rate, success rate, and average profit."""

    uptime = int(time.time() - _START_TIME)

    # Try to pull real metrics from DB
    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            # Active strategies
            strat_q = await session.execute(
                select(func.count()).select_from(StrategyConfig).where(StrategyConfig.is_enabled == True)  # noqa: E712
            )
            active_strategies = strat_q.scalar() or 0

            # Active exchanges
            ex_q = await session.execute(
                select(func.count()).select_from(Exchange).where(Exchange.is_active == True)  # noqa: E712
            )
            active_exchanges = ex_q.scalar() or 0

            # Pending executions
            pending_q = await session.execute(
                select(func.count())
                .select_from(ExecutionPlan)
                .where(
                    ExecutionPlan.status.in_([
                        ExecutionPlanStatus.PENDING,
                        ExecutionPlanStatus.SUBMITTING,
                        ExecutionPlanStatus.PARTIAL_FILLED,
                        ExecutionPlanStatus.HEDGING,
                    ])
                )
            )
            pending_executions = pending_q.scalar() or 0

            # Total and successful executions for rates
            total_exec_q = await session.execute(
                select(func.count()).select_from(ExecutionPlan)
            )
            total_executions = total_exec_q.scalar() or 0

            success_q = await session.execute(
                select(func.count())
                .select_from(ExecutionPlan)
                .where(ExecutionPlan.status == ExecutionPlanStatus.COMPLETED)
            )
            successful = success_q.scalar() or 0

            success_rate = Decimal(0)
            if total_executions > 0:
                success_rate = Decimal(str(round(successful / total_executions * 100, 2)))

            # Average profit
            avg_profit_q = await session.execute(
                select(func.avg(ExecutionPlan.actual_profit_usdt))
                .where(ExecutionPlan.status == ExecutionPlanStatus.COMPLETED)
            )
            avg_profit = avg_profit_q.scalar()
            avg_profit = Decimal(str(round(avg_profit or 0, 4)))

            return SystemMetrics(
                scan_rate=Decimal("0"),
                opportunity_rate=Decimal("0"),
                execution_rate=Decimal(str(round(total_executions / max(uptime / 60, 1), 2))),
                success_rate=success_rate,
                avg_profit=avg_profit,
                avg_slippage=Decimal("0"),
                risk_block_rate=Decimal("0"),
                uptime=uptime,
                active_strategies=active_strategies,
                active_exchanges=active_exchanges,
                pending_executions=pending_executions,
                timestamp=datetime.now(timezone.utc),
            )
    except Exception as exc:
        logger.debug("Failed to fetch live metrics, returning demo data: {}", exc)

    return SystemMetrics(
        scan_rate=Decimal(0),
        opportunity_rate=Decimal(0),
        execution_rate=Decimal(0),
        success_rate=Decimal(0),
        avg_profit=Decimal(0),
        avg_slippage=Decimal(0),
        risk_block_rate=Decimal(0),
        uptime=uptime,
        active_strategies=0,
        active_exchanges=0,
        pending_executions=0,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/exchanges",
    response_model=list[ExchangeStatus],
    summary="List configured exchanges with status",
)
async def list_exchanges() -> list[ExchangeStatus]:
    """Return all configured exchanges with their connectivity status."""

    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            result = await session.execute(select(Exchange))
            exchanges = result.scalars().all()
            if exchanges:
                statuses: list[ExchangeStatus] = []
                for ex in exchanges:
                    sym_count = len(ex.symbols) if ex.symbols else 0
                    statuses.append(
                        ExchangeStatus(
                            name=ex.name,
                            display_name=ex.display_name,
                            is_active=ex.is_active,
                            api_status=ex.api_status,
                            ws_status=ex.ws_status,
                            last_heartbeat=ex.last_heartbeat,
                            symbols_count=sym_count,
                        )
                    )
                return statuses
    except Exception as exc:
        logger.debug("Failed to fetch exchanges from DB: {}", exc)

    return []


@router.get(
    "/ws-status",
    response_model=list[WsStatus],
    summary="WebSocket connection status per exchange",
)
async def ws_status() -> list[WsStatus]:
    """Return the WebSocket connection status for each configured exchange."""

    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            result = await session.execute(select(Exchange))
            exchanges = result.scalars().all()
            if exchanges:
                statuses: list[WsStatus] = []
                for ex in exchanges:
                    statuses.append(
                        WsStatus(
                            exchange=ex.name,
                            connected=ex.ws_status == "CONNECTED",
                            subscribed_channels=[],
                            last_message_at=ex.last_heartbeat,
                            reconnect_count=0,
                            latency_ms=None,
                        )
                    )
                return statuses
    except Exception as exc:
        logger.debug("Failed to fetch WS status from DB: {}", exc)

    return []
