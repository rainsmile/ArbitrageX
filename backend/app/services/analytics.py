"""
AnalyticsService -- PnL summaries, slippage analysis, failure analysis,
and dashboard aggregation from the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, settings
from app.models.analytics import PnlRecord
from app.models.execution import ExecutionPlan, ExecutionPlanStatus
from app.models.opportunity import StrategyType


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TimeRange:
    """Time range for analytics queries."""
    start: datetime
    end: datetime

    @classmethod
    def last_hours(cls, hours: int) -> TimeRange:
        now = datetime.now(timezone.utc)
        return cls(start=now - timedelta(hours=hours), end=now)

    @classmethod
    def last_days(cls, days: int) -> TimeRange:
        now = datetime.now(timezone.utc)
        return cls(start=now - timedelta(days=days), end=now)

    @classmethod
    def today(cls) -> TimeRange:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return cls(start=start, end=now)


@dataclass(slots=True)
class PnlSummary:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    gross_profit_usdt: float = 0.0
    gross_loss_usdt: float = 0.0
    net_profit_usdt: float = 0.0
    total_fees_usdt: float = 0.0
    avg_profit_per_trade: float = 0.0
    win_rate: float = 0.0
    best_trade_usdt: float = 0.0
    worst_trade_usdt: float = 0.0
    avg_execution_time_ms: float = 0.0


@dataclass(slots=True)
class ProfitByPeriod:
    period: str  # e.g. "2025-01-15" or "2025-01-15T14"
    net_profit_usdt: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0


@dataclass(slots=True)
class ProfitByExchange:
    exchange: str
    net_profit_usdt: float = 0.0
    trade_count: int = 0
    avg_profit_usdt: float = 0.0
    total_fees_usdt: float = 0.0


@dataclass(slots=True)
class ProfitBySymbol:
    symbol: str
    net_profit_usdt: float = 0.0
    trade_count: int = 0
    avg_profit_usdt: float = 0.0
    win_rate: float = 0.0


@dataclass(slots=True)
class ProfitByStrategy:
    strategy: str
    net_profit_usdt: float = 0.0
    trade_count: int = 0
    avg_profit_usdt: float = 0.0
    win_rate: float = 0.0


@dataclass(slots=True)
class SlippageAnalysis:
    avg_slippage_usdt: float = 0.0
    max_slippage_usdt: float = 0.0
    total_slippage_usdt: float = 0.0
    avg_slippage_pct_of_trade: float = 0.0
    slippage_by_exchange: dict[str, float] = field(default_factory=dict)
    slippage_by_symbol: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class FailureAnalysis:
    total_failures: int = 0
    failure_rate: float = 0.0
    failures_by_status: dict[str, int] = field(default_factory=dict)
    avg_failure_time_ms: float = 0.0
    recent_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalyticsDashboard:
    pnl_summary: PnlSummary = field(default_factory=PnlSummary)
    profit_by_period: list[ProfitByPeriod] = field(default_factory=list)
    profit_by_exchange: list[ProfitByExchange] = field(default_factory=list)
    profit_by_symbol: list[ProfitBySymbol] = field(default_factory=list)
    profit_by_strategy: list[ProfitByStrategy] = field(default_factory=list)
    slippage: SlippageAnalysis = field(default_factory=SlippageAnalysis)
    failures: FailureAnalysis = field(default_factory=FailureAnalysis)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# AnalyticsService
# ---------------------------------------------------------------------------

class AnalyticsService:
    """Provides analytics queries over execution and PnL data.

    All queries use SQLAlchemy async with proper aggregation functions.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._cfg = config or settings

    # ------------------------------------------------------------------
    # PnL summary
    # ------------------------------------------------------------------

    async def get_pnl_summary(self, time_range: TimeRange) -> PnlSummary:
        """Aggregate PnL statistics for the given time range."""
        async with self._session_factory() as session:
            stmt = select(
                func.count(PnlRecord.id).label("total"),
                func.count(case((PnlRecord.net_profit_usdt > 0, 1))).label("wins"),
                func.count(case((PnlRecord.net_profit_usdt <= 0, 1))).label("losses"),
                func.coalesce(func.sum(case(
                    (PnlRecord.net_profit_usdt > 0, PnlRecord.net_profit_usdt),
                    else_=0,
                )), 0).label("gross_profit"),
                func.coalesce(func.sum(case(
                    (PnlRecord.net_profit_usdt <= 0, PnlRecord.net_profit_usdt),
                    else_=0,
                )), 0).label("gross_loss"),
                func.coalesce(func.sum(PnlRecord.net_profit_usdt), 0).label("net_profit"),
                func.coalesce(func.sum(PnlRecord.fees_usdt), 0).label("total_fees"),
                func.coalesce(func.avg(PnlRecord.net_profit_usdt), 0).label("avg_profit"),
                func.coalesce(func.max(PnlRecord.net_profit_usdt), 0).label("best_trade"),
                func.coalesce(func.min(PnlRecord.net_profit_usdt), 0).label("worst_trade"),
                func.coalesce(func.avg(PnlRecord.execution_time_ms), 0).label("avg_exec_time"),
            ).where(
                PnlRecord.created_at >= time_range.start,
                PnlRecord.created_at <= time_range.end,
            )

            result = await session.execute(stmt)
            row = result.one()

            total = row.total or 0
            wins = row.wins or 0

            return PnlSummary(
                total_trades=total,
                winning_trades=wins,
                losing_trades=row.losses or 0,
                gross_profit_usdt=float(row.gross_profit or 0),
                gross_loss_usdt=float(row.gross_loss or 0),
                net_profit_usdt=float(row.net_profit or 0),
                total_fees_usdt=float(row.total_fees or 0),
                avg_profit_per_trade=float(row.avg_profit or 0),
                win_rate=(wins / total * 100.0) if total > 0 else 0.0,
                best_trade_usdt=float(row.best_trade or 0),
                worst_trade_usdt=float(row.worst_trade or 0),
                avg_execution_time_ms=float(row.avg_exec_time or 0),
            )

    # ------------------------------------------------------------------
    # Profit by period
    # ------------------------------------------------------------------

    async def get_profit_by_period(
        self,
        period: str,
        time_range: TimeRange,
    ) -> list[ProfitByPeriod]:
        """Aggregate profit grouped by time period.

        *period* can be ``"hour"``, ``"day"``, or ``"week"``.
        """
        if period == "hour":
            trunc_fn = func.date_format(PnlRecord.created_at, "%Y-%m-%d %H:00:00")
            fmt = "%Y-%m-%dT%H"
        elif period == "week":
            trunc_fn = func.yearweek(PnlRecord.created_at)
            fmt = "%Y-W%W"
        else:
            trunc_fn = func.date_format(PnlRecord.created_at, "%Y-%m-%d")
            fmt = "%Y-%m-%d"

        async with self._session_factory() as session:
            stmt = (
                select(
                    trunc_fn.label("period"),
                    func.coalesce(func.sum(PnlRecord.net_profit_usdt), 0).label("net_profit"),
                    func.count(PnlRecord.id).label("trade_count"),
                    func.count(case((PnlRecord.net_profit_usdt > 0, 1))).label("wins"),
                )
                .where(
                    PnlRecord.created_at >= time_range.start,
                    PnlRecord.created_at <= time_range.end,
                )
                .group_by("period")
                .order_by("period")
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                ProfitByPeriod(
                    period=row.period.strftime(fmt) if hasattr(row.period, "strftime") else str(row.period),
                    net_profit_usdt=float(row.net_profit or 0),
                    trade_count=row.trade_count or 0,
                    win_rate=(row.wins / row.trade_count * 100.0) if row.trade_count > 0 else 0.0,
                )
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Profit by exchange
    # ------------------------------------------------------------------

    async def get_profit_by_exchange(
        self, time_range: TimeRange
    ) -> list[ProfitByExchange]:
        """Aggregate profit by exchange (buy-side exchange)."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    PnlRecord.exchange_buy.label("exchange"),
                    func.coalesce(func.sum(PnlRecord.net_profit_usdt), 0).label("net_profit"),
                    func.count(PnlRecord.id).label("trade_count"),
                    func.coalesce(func.avg(PnlRecord.net_profit_usdt), 0).label("avg_profit"),
                    func.coalesce(func.sum(PnlRecord.fees_usdt), 0).label("total_fees"),
                )
                .where(
                    PnlRecord.created_at >= time_range.start,
                    PnlRecord.created_at <= time_range.end,
                )
                .group_by(PnlRecord.exchange_buy)
                .order_by(func.sum(PnlRecord.net_profit_usdt).desc())
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                ProfitByExchange(
                    exchange=row.exchange or "unknown",
                    net_profit_usdt=float(row.net_profit or 0),
                    trade_count=row.trade_count or 0,
                    avg_profit_usdt=float(row.avg_profit or 0),
                    total_fees_usdt=float(row.total_fees or 0),
                )
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Profit by symbol
    # ------------------------------------------------------------------

    async def get_profit_by_symbol(
        self, time_range: TimeRange
    ) -> list[ProfitBySymbol]:
        """Aggregate profit by trading symbol."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    PnlRecord.symbol,
                    func.coalesce(func.sum(PnlRecord.net_profit_usdt), 0).label("net_profit"),
                    func.count(PnlRecord.id).label("trade_count"),
                    func.coalesce(func.avg(PnlRecord.net_profit_usdt), 0).label("avg_profit"),
                    func.count(case((PnlRecord.net_profit_usdt > 0, 1))).label("wins"),
                )
                .where(
                    PnlRecord.created_at >= time_range.start,
                    PnlRecord.created_at <= time_range.end,
                )
                .group_by(PnlRecord.symbol)
                .order_by(func.sum(PnlRecord.net_profit_usdt).desc())
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                ProfitBySymbol(
                    symbol=row.symbol or "unknown",
                    net_profit_usdt=float(row.net_profit or 0),
                    trade_count=row.trade_count or 0,
                    avg_profit_usdt=float(row.avg_profit or 0),
                    win_rate=(row.wins / row.trade_count * 100.0) if row.trade_count > 0 else 0.0,
                )
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Profit by strategy
    # ------------------------------------------------------------------

    async def get_profit_by_strategy(
        self, time_range: TimeRange
    ) -> list[ProfitByStrategy]:
        """Aggregate profit by strategy type."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    PnlRecord.strategy_type,
                    func.coalesce(func.sum(PnlRecord.net_profit_usdt), 0).label("net_profit"),
                    func.count(PnlRecord.id).label("trade_count"),
                    func.coalesce(func.avg(PnlRecord.net_profit_usdt), 0).label("avg_profit"),
                    func.count(case((PnlRecord.net_profit_usdt > 0, 1))).label("wins"),
                )
                .where(
                    PnlRecord.created_at >= time_range.start,
                    PnlRecord.created_at <= time_range.end,
                )
                .group_by(PnlRecord.strategy_type)
                .order_by(func.sum(PnlRecord.net_profit_usdt).desc())
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                ProfitByStrategy(
                    strategy=row.strategy_type.value if hasattr(row.strategy_type, "value") else str(row.strategy_type),
                    net_profit_usdt=float(row.net_profit or 0),
                    trade_count=row.trade_count or 0,
                    avg_profit_usdt=float(row.avg_profit or 0),
                    win_rate=(row.wins / row.trade_count * 100.0) if row.trade_count > 0 else 0.0,
                )
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Slippage analysis
    # ------------------------------------------------------------------

    async def get_slippage_analysis(
        self, time_range: TimeRange
    ) -> SlippageAnalysis:
        """Analyse slippage across trades."""
        async with self._session_factory() as session:
            # Overall slippage stats
            stmt = select(
                func.coalesce(func.avg(PnlRecord.slippage_usdt), 0).label("avg_slippage"),
                func.coalesce(func.max(PnlRecord.slippage_usdt), 0).label("max_slippage"),
                func.coalesce(func.sum(PnlRecord.slippage_usdt), 0).label("total_slippage"),
            ).where(
                PnlRecord.created_at >= time_range.start,
                PnlRecord.created_at <= time_range.end,
            )
            result = await session.execute(stmt)
            row = result.one()

            analysis = SlippageAnalysis(
                avg_slippage_usdt=float(row.avg_slippage or 0),
                max_slippage_usdt=float(row.max_slippage or 0),
                total_slippage_usdt=float(row.total_slippage or 0),
            )

            # Slippage as pct of trade
            pct_stmt = select(
                func.coalesce(
                    func.avg(
                        case(
                            (PnlRecord.gross_profit_usdt != 0,
                             PnlRecord.slippage_usdt / func.abs(PnlRecord.gross_profit_usdt) * 100),
                            else_=0,
                        )
                    ), 0
                ).label("avg_pct"),
            ).where(
                PnlRecord.created_at >= time_range.start,
                PnlRecord.created_at <= time_range.end,
            )
            pct_result = await session.execute(pct_stmt)
            pct_row = pct_result.one()
            analysis.avg_slippage_pct_of_trade = float(pct_row.avg_pct or 0)

            # Slippage by exchange (buy side)
            exch_stmt = (
                select(
                    PnlRecord.exchange_buy.label("exchange"),
                    func.coalesce(func.avg(PnlRecord.slippage_usdt), 0).label("avg_slippage"),
                )
                .where(
                    PnlRecord.created_at >= time_range.start,
                    PnlRecord.created_at <= time_range.end,
                )
                .group_by(PnlRecord.exchange_buy)
            )
            exch_result = await session.execute(exch_stmt)
            for row in exch_result.all():
                if row.exchange:
                    analysis.slippage_by_exchange[row.exchange] = float(row.avg_slippage or 0)

            # Slippage by symbol
            sym_stmt = (
                select(
                    PnlRecord.symbol,
                    func.coalesce(func.avg(PnlRecord.slippage_usdt), 0).label("avg_slippage"),
                )
                .where(
                    PnlRecord.created_at >= time_range.start,
                    PnlRecord.created_at <= time_range.end,
                )
                .group_by(PnlRecord.symbol)
            )
            sym_result = await session.execute(sym_stmt)
            for row in sym_result.all():
                if row.symbol:
                    analysis.slippage_by_symbol[row.symbol] = float(row.avg_slippage or 0)

            return analysis

    # ------------------------------------------------------------------
    # Failure analysis
    # ------------------------------------------------------------------

    async def get_failure_analysis(
        self, time_range: TimeRange
    ) -> FailureAnalysis:
        """Analyse execution failures."""
        async with self._session_factory() as session:
            # Total executions and failures
            total_stmt = select(
                func.count(ExecutionPlan.id).label("total"),
                func.count(case((ExecutionPlan.status == ExecutionPlanStatus.FAILED, 1))).label("failures"),
            ).where(
                ExecutionPlan.started_at >= time_range.start,
                ExecutionPlan.started_at <= time_range.end,
            )
            total_result = await session.execute(total_stmt)
            total_row = total_result.one()
            total = total_row.total or 0
            failures = total_row.failures or 0

            analysis = FailureAnalysis(
                total_failures=failures,
                failure_rate=(failures / total * 100.0) if total > 0 else 0.0,
            )

            # Failures by status
            status_stmt = (
                select(
                    ExecutionPlan.status,
                    func.count(ExecutionPlan.id).label("count"),
                )
                .where(
                    ExecutionPlan.started_at >= time_range.start,
                    ExecutionPlan.started_at <= time_range.end,
                    ExecutionPlan.status.in_([
                        ExecutionPlanStatus.FAILED,
                        ExecutionPlanStatus.ABORTED,
                        ExecutionPlanStatus.HEDGING,
                    ]),
                )
                .group_by(ExecutionPlan.status)
            )
            status_result = await session.execute(status_stmt)
            for row in status_result.all():
                status_name = row.status.value if hasattr(row.status, "value") else str(row.status)
                analysis.failures_by_status[status_name] = row.count or 0

            # Average failure time
            fail_time_stmt = select(
                func.coalesce(func.avg(ExecutionPlan.execution_time_ms), 0).label("avg_time"),
            ).where(
                ExecutionPlan.started_at >= time_range.start,
                ExecutionPlan.started_at <= time_range.end,
                ExecutionPlan.status == ExecutionPlanStatus.FAILED,
            )
            fail_time_result = await session.execute(fail_time_stmt)
            fail_time_row = fail_time_result.one()
            analysis.avg_failure_time_ms = float(fail_time_row.avg_time or 0)

            # Recent error messages
            errors_stmt = (
                select(ExecutionPlan.error_message)
                .where(
                    ExecutionPlan.started_at >= time_range.start,
                    ExecutionPlan.started_at <= time_range.end,
                    ExecutionPlan.status == ExecutionPlanStatus.FAILED,
                    ExecutionPlan.error_message.isnot(None),
                )
                .order_by(ExecutionPlan.started_at.desc())
                .limit(10)
            )
            errors_result = await session.execute(errors_stmt)
            analysis.recent_errors = [
                row.error_message for row in errors_result.all()
                if row.error_message
            ]

            return analysis

    # ------------------------------------------------------------------
    # Full dashboard
    # ------------------------------------------------------------------

    async def get_dashboard(
        self,
        time_range: TimeRange | None = None,
    ) -> AnalyticsDashboard:
        """Build a complete analytics dashboard."""
        if time_range is None:
            time_range = TimeRange.last_days(7)

        try:
            pnl_summary = await self.get_pnl_summary(time_range)
            profit_by_period = await self.get_profit_by_period("day", time_range)
            profit_by_exchange = await self.get_profit_by_exchange(time_range)
            profit_by_symbol = await self.get_profit_by_symbol(time_range)
            profit_by_strategy = await self.get_profit_by_strategy(time_range)
            slippage = await self.get_slippage_analysis(time_range)
            failures = await self.get_failure_analysis(time_range)

            return AnalyticsDashboard(
                pnl_summary=pnl_summary,
                profit_by_period=profit_by_period,
                profit_by_exchange=profit_by_exchange,
                profit_by_symbol=profit_by_symbol,
                profit_by_strategy=profit_by_strategy,
                slippage=slippage,
                failures=failures,
            )
        except Exception:
            logger.opt(exception=True).error("Failed to build analytics dashboard")
            return AnalyticsDashboard()
