"""
Analytics and PnL endpoints.

Router prefix: /api/analytics
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.analytics import PnlRecord
from app.models.execution import ExecutionPlan, ExecutionPlanStatus
from app.schemas.analytics import (
    AnalyticsDashboard,
    FailureAnalysis,
    PnlSummary,
    ProfitByExchange,
    ProfitByPeriod,
    ProfitByStrategy,
    ProfitBySymbol,
    SlippageAnalysis,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_time_range(
    start: Optional[datetime],
    end: Optional[datetime],
) -> tuple[datetime, datetime]:
    """Return (start, end) falling back to last 24 hours."""
    now = datetime.now(timezone.utc)
    return (start or now - timedelta(days=1), end or now)


def _empty_pnl_summary(period_start: datetime, period_end: datetime) -> PnlSummary:
    """Return an empty PnL summary when no data is available."""
    return PnlSummary(
        total_gross_profit_usdt=Decimal(0),
        total_fees_usdt=Decimal(0),
        total_net_profit_usdt=Decimal(0),
        total_slippage_usdt=Decimal(0),
        trade_count=0,
        win_count=0,
        loss_count=0,
        win_rate=Decimal(0),
        avg_profit_per_trade_usdt=Decimal(0),
        max_profit_usdt=Decimal(0),
        max_loss_usdt=Decimal(0),
        sharpe_ratio=None,
        period_start=period_start,
        period_end=period_end,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=PnlSummary,
    summary="PnL summary",
)
async def get_pnl_summary(
    start: Optional[datetime] = Query(None, description="Period start (ISO8601)"),
    end: Optional[datetime] = Query(None, description="Period end (ISO8601)"),
    db: AsyncSession = Depends(get_db),
) -> PnlSummary:
    """Return an aggregated PnL summary for the given time range (default: last 24h)."""

    period_start, period_end = _default_time_range(start, end)

    try:
        result = await db.execute(
            select(
                func.sum(PnlRecord.gross_profit_usdt),
                func.sum(PnlRecord.fees_usdt),
                func.sum(PnlRecord.net_profit_usdt),
                func.sum(PnlRecord.slippage_usdt),
                func.count(PnlRecord.id),
                func.sum(case((PnlRecord.net_profit_usdt > 0, 1), else_=0)),
                func.sum(case((PnlRecord.net_profit_usdt <= 0, 1), else_=0)),
                func.avg(PnlRecord.net_profit_usdt),
                func.max(PnlRecord.net_profit_usdt),
                func.min(PnlRecord.net_profit_usdt),
            ).where(
                PnlRecord.created_at.between(period_start, period_end)
            )
        )
        row = result.one()
        gross, fees, net, slippage, count, wins, losses, avg_p, max_p, min_p = row

        if count and count > 0:
            win_rate = Decimal(str(round((wins or 0) / count * 100, 2)))

            # Calculate total traded volume from execution_plans to derive PnL %
            vol_result = await db.execute(
                select(func.sum(ExecutionPlan.target_value_usdt)).where(
                    ExecutionPlan.started_at.between(period_start, period_end)
                )
            )
            total_volume = vol_result.scalar() or 0
            total_volume_dec = Decimal(str(total_volume))
            net_dec = Decimal(str(net or 0))
            pnl_pct = (
                Decimal(str(round(float(net_dec / total_volume_dec * 100), 4)))
                if total_volume_dec > 0
                else None
            )

            return PnlSummary(
                total_gross_profit_usdt=Decimal(str(gross or 0)),
                total_fees_usdt=Decimal(str(fees or 0)),
                total_net_profit_usdt=Decimal(str(net or 0)),
                total_slippage_usdt=Decimal(str(slippage or 0)),
                trade_count=count,
                win_count=wins or 0,
                loss_count=losses or 0,
                win_rate=win_rate,
                avg_profit_per_trade_usdt=Decimal(str(round(avg_p or 0, 4))),
                max_profit_usdt=Decimal(str(max_p or 0)),
                max_loss_usdt=Decimal(str(min_p or 0)),
                total_volume_usdt=total_volume_dec,
                total_pnl_percent=pnl_pct,
                sharpe_ratio=None,
                period_start=period_start,
                period_end=period_end,
            )
    except Exception as exc:
        logger.debug("Failed to compute PnL summary: {}", exc)

    return _empty_pnl_summary(period_start, period_end)


@router.get(
    "/profit",
    response_model=list[ProfitByPeriod],
    summary="Profit by time period",
)
async def get_profit_by_period(
    period: str = Query("hour", description="Aggregation period: hour, day, or week"),
    start: Optional[datetime] = Query(None, description="Period start (ISO8601)"),
    end: Optional[datetime] = Query(None, description="Period end (ISO8601)"),
    db: AsyncSession = Depends(get_db),
) -> list[ProfitByPeriod]:
    """Return profit aggregated by time bucket (hourly, daily, or weekly)."""

    if period not in ("hour", "day", "week"):
        period = "hour"

    period_start, period_end = _default_time_range(start, end)

    try:
        # Use MySQL date_format / yearweek for grouping
        if period == "hour":
            trunc_expr = func.date_format(PnlRecord.created_at, "%Y-%m-%d %H:00:00")
        elif period == "week":
            trunc_expr = func.yearweek(PnlRecord.created_at)
        else:
            trunc_expr = func.date_format(PnlRecord.created_at, "%Y-%m-%d")

        result = await db.execute(
            select(
                trunc_expr.label("bucket"),
                func.sum(PnlRecord.gross_profit_usdt),
                func.sum(PnlRecord.net_profit_usdt),
                func.sum(PnlRecord.fees_usdt),
                func.count(PnlRecord.id),
            )
            .where(PnlRecord.created_at.between(period_start, period_end))
            .group_by("bucket")
            .order_by("bucket")
        )
        rows = result.all()

        if rows:
            items: list[ProfitByPeriod] = []
            for bucket, gross, net, fees, count in rows:
                fmt = "%Y-%m-%dT%H:00" if period == "hour" else "%Y-%m-%d"
                items.append(
                    ProfitByPeriod(
                        period=bucket.strftime(fmt) if bucket else "unknown",
                        gross_profit_usdt=Decimal(str(gross or 0)),
                        net_profit_usdt=Decimal(str(net or 0)),
                        fees_usdt=Decimal(str(fees or 0)),
                        trade_count=count or 0,
                    )
                )
            return items
    except Exception as exc:
        logger.debug("Failed to compute profit by period: {}", exc)

    return []


@router.get(
    "/profit/by-exchange",
    response_model=list[ProfitByExchange],
    summary="Profit grouped by exchange pair",
)
async def get_profit_by_exchange(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ProfitByExchange]:
    """Return PnL breakdown grouped by buy/sell exchange pair."""

    period_start, period_end = _default_time_range(start, end)

    try:
        result = await db.execute(
            select(
                PnlRecord.exchange_buy,
                PnlRecord.exchange_sell,
                func.sum(PnlRecord.net_profit_usdt),
                func.count(PnlRecord.id),
                func.avg(PnlRecord.net_profit_usdt),
                func.sum(case((PnlRecord.net_profit_usdt > 0, 1), else_=0)),
            )
            .where(PnlRecord.created_at.between(period_start, period_end))
            .group_by(PnlRecord.exchange_buy, PnlRecord.exchange_sell)
            .order_by(func.sum(PnlRecord.net_profit_usdt).desc())
        )
        rows = result.all()

        if rows:
            items: list[ProfitByExchange] = []
            for buy_ex, sell_ex, net, count, avg_p, wins in rows:
                win_rate = Decimal(str(round((wins or 0) / count * 100, 2))) if count else Decimal(0)
                items.append(
                    ProfitByExchange(
                        exchange_buy=buy_ex or "unknown",
                        exchange_sell=sell_ex or "unknown",
                        net_profit_usdt=Decimal(str(net or 0)),
                        trade_count=count or 0,
                        avg_profit_usdt=Decimal(str(round(avg_p or 0, 4))),
                        win_rate=win_rate,
                    )
                )
            return items
    except Exception as exc:
        logger.debug("Failed to compute profit by exchange: {}", exc)

    return []


@router.get(
    "/profit/by-symbol",
    response_model=list[ProfitBySymbol],
    summary="Profit grouped by symbol",
)
async def get_profit_by_symbol(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ProfitBySymbol]:
    """Return PnL breakdown grouped by trading symbol."""

    period_start, period_end = _default_time_range(start, end)

    try:
        result = await db.execute(
            select(
                PnlRecord.symbol,
                func.sum(PnlRecord.net_profit_usdt),
                func.count(PnlRecord.id),
                func.avg(PnlRecord.net_profit_usdt),
                func.sum(case((PnlRecord.net_profit_usdt > 0, 1), else_=0)),
            )
            .where(PnlRecord.created_at.between(period_start, period_end))
            .group_by(PnlRecord.symbol)
            .order_by(func.sum(PnlRecord.net_profit_usdt).desc())
        )
        rows = result.all()

        if rows:
            items: list[ProfitBySymbol] = []
            for symbol, net, count, avg_p, wins in rows:
                win_rate = Decimal(str(round((wins or 0) / count * 100, 2))) if count else Decimal(0)
                items.append(
                    ProfitBySymbol(
                        symbol=symbol,
                        net_profit_usdt=Decimal(str(net or 0)),
                        trade_count=count or 0,
                        avg_profit_usdt=Decimal(str(round(avg_p or 0, 4))),
                        win_rate=win_rate,
                    )
                )
            return items
    except Exception as exc:
        logger.debug("Failed to compute profit by symbol: {}", exc)

    return []


@router.get(
    "/profit/by-strategy",
    response_model=list[ProfitByStrategy],
    summary="Profit grouped by strategy",
)
async def get_profit_by_strategy(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ProfitByStrategy]:
    """Return PnL breakdown grouped by strategy type."""

    period_start, period_end = _default_time_range(start, end)

    try:
        result = await db.execute(
            select(
                PnlRecord.strategy_type,
                func.sum(PnlRecord.net_profit_usdt),
                func.count(PnlRecord.id),
                func.avg(PnlRecord.net_profit_usdt),
                func.sum(case((PnlRecord.net_profit_usdt > 0, 1), else_=0)),
            )
            .where(PnlRecord.created_at.between(period_start, period_end))
            .group_by(PnlRecord.strategy_type)
            .order_by(func.sum(PnlRecord.net_profit_usdt).desc())
        )
        rows = result.all()

        if rows:
            items: list[ProfitByStrategy] = []
            for strat_type, net, count, avg_p, wins in rows:
                win_rate = Decimal(str(round((wins or 0) / count * 100, 2))) if count else Decimal(0)
                items.append(
                    ProfitByStrategy(
                        strategy_type=strat_type.value if hasattr(strat_type, "value") else str(strat_type),
                        net_profit_usdt=Decimal(str(net or 0)),
                        trade_count=count or 0,
                        avg_profit_usdt=Decimal(str(round(avg_p or 0, 4))),
                        win_rate=win_rate,
                    )
                )
            return items
    except Exception as exc:
        logger.debug("Failed to compute profit by strategy: {}", exc)

    return []


@router.get(
    "/failures",
    response_model=FailureAnalysis,
    summary="Failure analysis",
)
async def get_failure_analysis(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> FailureAnalysis:
    """Return analysis of failed and aborted executions."""

    period_start, period_end = _default_time_range(start, end)

    try:
        # Count failures and aborts
        result = await db.execute(
            select(
                func.sum(case((ExecutionPlan.status == ExecutionPlanStatus.FAILED, 1), else_=0)),
                func.sum(case((ExecutionPlan.status == ExecutionPlanStatus.ABORTED, 1), else_=0)),
                func.count(ExecutionPlan.id),
            ).where(ExecutionPlan.created_at.between(period_start, period_end))
        )
        row = result.one()
        failures, aborted, total = row

        failures = failures or 0
        aborted = aborted or 0
        total = total or 0

        failure_rate = Decimal(str(round((failures + aborted) / total * 100, 2))) if total > 0 else Decimal(0)

        if total > 0:
            return FailureAnalysis(
                total_failures=failures,
                total_aborted=aborted,
                failure_rate=failure_rate,
                top_failure_reasons=[],
                failures_by_exchange={},
                failures_by_symbol={},
            )
    except Exception as exc:
        logger.debug("Failed to compute failure analysis: {}", exc)

    return FailureAnalysis(
        total_failures=0,
        total_aborted=0,
        failure_rate=Decimal(0),
        top_failure_reasons=[],
        failures_by_exchange={},
        failures_by_symbol={},
    )


@router.get(
    "/slippage",
    response_model=SlippageAnalysis,
    summary="Slippage analysis",
)
async def get_slippage_analysis(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> SlippageAnalysis:
    """Return analysis of execution slippage."""

    period_start, period_end = _default_time_range(start, end)

    try:
        from app.models.execution import ExecutionLeg

        result = await db.execute(
            select(
                func.avg(ExecutionLeg.slippage_pct),
                func.max(ExecutionLeg.slippage_pct),
                func.count(ExecutionLeg.id),
            ).where(
                ExecutionLeg.created_at.between(period_start, period_end),
                ExecutionLeg.slippage_pct.isnot(None),
            )
        )
        row = result.one()
        avg_slip, max_slip, count = row

        if count and count > 0:
            # Compute total slippage from PnlRecord
            slip_result = await db.execute(
                select(func.sum(PnlRecord.slippage_usdt))
                .where(PnlRecord.created_at.between(period_start, period_end))
            )
            total_slip_usdt = slip_result.scalar() or 0

            return SlippageAnalysis(
                avg_slippage_pct=Decimal(str(round(avg_slip or 0, 4))),
                median_slippage_pct=Decimal(str(round(avg_slip or 0, 4))),  # approximation
                max_slippage_pct=Decimal(str(round(max_slip or 0, 4))),
                total_slippage_usdt=Decimal(str(total_slip_usdt)),
                slippage_by_exchange={},
                slippage_by_symbol={},
                sample_count=count,
            )
    except Exception as exc:
        logger.debug("Failed to compute slippage analysis: {}", exc)

    return SlippageAnalysis(
        avg_slippage_pct=Decimal(0),
        median_slippage_pct=Decimal(0),
        max_slippage_pct=Decimal(0),
        total_slippage_usdt=Decimal(0),
        slippage_by_exchange={},
        slippage_by_symbol={},
        sample_count=0,
    )


@router.get(
    "/dashboard",
    response_model=AnalyticsDashboard,
    summary="Combined analytics dashboard",
)
async def get_dashboard(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsDashboard:
    """Return a combined analytics dashboard with all analytics views."""

    pnl = await get_pnl_summary(start, end, db)
    profit_period = await get_profit_by_period("hour", start, end, db)
    profit_exchange = await get_profit_by_exchange(start, end, db)
    profit_symbol = await get_profit_by_symbol(start, end, db)
    profit_strategy = await get_profit_by_strategy(start, end, db)
    slippage = await get_slippage_analysis(start, end, db)
    failures = await get_failure_analysis(start, end, db)

    # Recent executions (last 10 completed/failed)
    recent_executions: list[dict] = []
    try:
        exec_result = await db.execute(
            select(
                ExecutionPlan.id,
                ExecutionPlan.strategy_type,
                ExecutionPlan.status,
                ExecutionPlan.actual_profit_usdt,
                ExecutionPlan.actual_profit_pct,
                ExecutionPlan.execution_time_ms,
                ExecutionPlan.completed_at,
                ExecutionPlan.started_at,
            )
            .where(
                ExecutionPlan.status.in_([
                    ExecutionPlanStatus.COMPLETED,
                    ExecutionPlanStatus.FAILED,
                    ExecutionPlanStatus.ABORTED,
                ])
            )
            .order_by(ExecutionPlan.completed_at.desc())
            .limit(10)
        )
        for row in exec_result.all():
            eid, stype, st, profit, profit_pct, etime, completed, started = row
            recent_executions.append({
                "execution_id": str(eid),
                "strategy_type": stype.value if hasattr(stype, "value") else str(stype),
                "state": st.value if hasattr(st, "value") else str(st),
                "actual_profit_usdt": float(profit) if profit else 0,
                "actual_profit_pct": float(profit_pct) if profit_pct else 0,
                "execution_time_ms": etime or 0,
                "completed_at": completed.timestamp() if completed else None,
                "started_at": started.timestamp() if started else None,
            })
    except Exception as exc:
        logger.debug("Failed to fetch recent executions for dashboard: {}", exc)

    # Top opportunities (active, sorted by estimated net profit)
    top_opportunities: list[dict] = []
    try:
        from app.models.opportunity import ArbitrageOpportunity, OpportunityStatus

        opp_result = await db.execute(
            select(ArbitrageOpportunity)
            .where(ArbitrageOpportunity.status == OpportunityStatus.DETECTED)
            .order_by(ArbitrageOpportunity.estimated_net_profit_pct.desc())
            .limit(10)
        )
        for row in opp_result.scalars().all():
            top_opportunities.append({
                "id": str(row.id),
                "strategy_type": row.strategy_type.value if hasattr(row.strategy_type, "value") else str(row.strategy_type),
                "symbol": (row.symbols[0] if row.symbols else ""),
                "buy_exchange": row.buy_exchange or "",
                "sell_exchange": row.sell_exchange or "",
                "buy_price": float(row.buy_price) if row.buy_price else 0,
                "sell_price": float(row.sell_price) if row.sell_price else 0,
                "spread_pct": float(row.spread_pct) if row.spread_pct else 0,
                "theoretical_profit_pct": float(row.theoretical_profit_pct) if row.theoretical_profit_pct else 0,
                "estimated_net_profit_pct": float(row.estimated_net_profit_pct) if row.estimated_net_profit_pct else 0,
                "executable_quantity": float(row.executable_quantity) if row.executable_quantity else 0,
                "executable_value_usdt": float(row.executable_value_usdt) if row.executable_value_usdt else 0,
                "confidence_score": float(row.confidence_score) if row.confidence_score else 0,
                "detected_at": row.detected_at.timestamp() if row.detected_at else None,
                "buy_fee_pct": float(row.buy_fee_pct) if row.buy_fee_pct else 0,
                "sell_fee_pct": float(row.sell_fee_pct) if row.sell_fee_pct else 0,
            })
    except Exception as exc:
        logger.debug("Failed to fetch top opportunities for dashboard: {}", exc)

    return AnalyticsDashboard(
        pnl_summary=pnl,
        profit_by_period=profit_period,
        profit_by_exchange=profit_exchange,
        profit_by_symbol=profit_symbol,
        profit_by_strategy=profit_strategy,
        slippage=slippage,
        failures=failures,
        recent_executions=recent_executions,
        top_opportunities=top_opportunities,
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/opportunity-vs-execution",
    response_model=list[dict],
    summary="Theoretical vs actual profit comparison",
)
async def get_opportunity_vs_execution(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Compare theoretical opportunity profit with actual execution profit."""

    period_start, period_end = _default_time_range(start, end)

    try:
        from app.models.opportunity import ArbitrageOpportunity

        result = await db.execute(
            select(
                ExecutionPlan.id,
                ExecutionPlan.planned_profit_pct,
                ExecutionPlan.actual_profit_pct,
                ExecutionPlan.actual_profit_usdt,
                ExecutionPlan.execution_time_ms,
                ExecutionPlan.status,
                ArbitrageOpportunity.theoretical_profit_pct,
                ArbitrageOpportunity.estimated_net_profit_pct,
                ArbitrageOpportunity.spread_pct,
            )
            .join(ArbitrageOpportunity, ExecutionPlan.opportunity_id == ArbitrageOpportunity.id, isouter=True)
            .where(ExecutionPlan.created_at.between(period_start, period_end))
            .order_by(ExecutionPlan.created_at.desc())
            .limit(limit)
        )
        rows = result.all()

        if rows:
            comparisons = []
            for row in rows:
                comparisons.append({
                    "execution_id": str(row[0]),
                    "planned_profit_pct": float(row[1]) if row[1] else None,
                    "actual_profit_pct": float(row[2]) if row[2] else None,
                    "actual_profit_usdt": float(row[3]) if row[3] else None,
                    "execution_time_ms": row[4],
                    "execution_status": row[5].value if hasattr(row[5], "value") else str(row[5]),
                    "theoretical_profit_pct": float(row[6]) if row[6] else None,
                    "estimated_net_profit_pct": float(row[7]) if row[7] else None,
                    "spread_pct": float(row[8]) if row[8] else None,
                    "profit_deviation_pct": (
                        round(float(row[2]) - float(row[1]), 4)
                        if row[1] and row[2] else None
                    ),
                })
            return comparisons
    except Exception as exc:
        logger.debug("Failed to compute opp vs exec: {}", exc)

    return []
