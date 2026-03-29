"""
Analytics and PnL Pydantic schemas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# PnL summary
# ---------------------------------------------------------------------------


class PnlSummary(BaseModel):
    """Aggregated PnL overview for a given time range."""

    total_gross_profit_usdt: Decimal = Field(description="Total gross profit before fees (USDT)")
    total_fees_usdt: Decimal = Field(description="Total fees paid (USDT)")
    total_net_profit_usdt: Decimal = Field(description="Total net profit after fees (USDT)")
    total_slippage_usdt: Decimal = Field(description="Total slippage cost (USDT)")
    trade_count: int = Field(ge=0, description="Number of completed trades in the period")
    win_count: int = Field(ge=0, description="Number of profitable trades")
    loss_count: int = Field(ge=0, description="Number of unprofitable trades")
    win_rate: Decimal = Field(ge=0, le=100, description="Win rate as percentage")
    avg_profit_per_trade_usdt: Decimal = Field(description="Average net profit per trade (USDT)")
    max_profit_usdt: Decimal = Field(description="Largest single-trade profit (USDT)")
    max_loss_usdt: Decimal = Field(description="Largest single-trade loss (USDT)")
    total_volume_usdt: Decimal = Field(default=Decimal(0), description="Total traded volume (USDT)")
    total_pnl_percent: Optional[Decimal] = Field(default=None, description="Net profit as % of traded volume")
    sharpe_ratio: Optional[Decimal] = Field(default=None, description="Sharpe ratio if enough samples exist")
    period_start: datetime = Field(description="Start of the reporting period")
    period_end: datetime = Field(description="End of the reporting period")


# ---------------------------------------------------------------------------
# Breakdown schemas
# ---------------------------------------------------------------------------


class ProfitByPeriod(BaseModel):
    """PnL aggregated into a time bucket (e.g. hourly, daily)."""

    period: str = Field(description="Period label (e.g. '2026-03-28', '2026-03-28T14:00')")
    gross_profit_usdt: Decimal = Field(description="Gross profit for the period")
    net_profit_usdt: Decimal = Field(description="Net profit for the period")
    fees_usdt: Decimal = Field(description="Fees for the period")
    trade_count: int = Field(ge=0, description="Number of trades in this period")


class ProfitByExchange(BaseModel):
    """PnL breakdown for a specific exchange pair (buy_exchange -> sell_exchange)."""

    exchange_buy: str = Field(description="Buy-side exchange")
    exchange_sell: str = Field(description="Sell-side exchange")
    net_profit_usdt: Decimal = Field(description="Total net profit for this exchange pair")
    trade_count: int = Field(ge=0, description="Number of trades for this exchange pair")
    avg_profit_usdt: Decimal = Field(description="Average net profit per trade")
    win_rate: Decimal = Field(ge=0, le=100, description="Win rate as percentage")


class ProfitBySymbol(BaseModel):
    """PnL breakdown for a specific trading symbol."""

    symbol: str = Field(description="Unified symbol (e.g. BTC/USDT)")
    net_profit_usdt: Decimal = Field(description="Total net profit for this symbol")
    trade_count: int = Field(ge=0, description="Number of trades for this symbol")
    avg_profit_usdt: Decimal = Field(description="Average net profit per trade")
    win_rate: Decimal = Field(ge=0, le=100, description="Win rate as percentage")


class ProfitByStrategy(BaseModel):
    """PnL breakdown for a specific strategy type."""

    strategy_type: str = Field(description="Strategy type (CROSS_EXCHANGE, TRIANGULAR, FUTURES_SPOT)")
    net_profit_usdt: Decimal = Field(description="Total net profit for this strategy")
    trade_count: int = Field(ge=0, description="Number of trades for this strategy")
    avg_profit_usdt: Decimal = Field(description="Average net profit per trade")
    win_rate: Decimal = Field(ge=0, le=100, description="Win rate as percentage")


# ---------------------------------------------------------------------------
# Deep-dive analytics
# ---------------------------------------------------------------------------


class SlippageAnalysis(BaseModel):
    """Analysis of slippage across executions."""

    avg_slippage_pct: Decimal = Field(description="Average slippage as percentage of planned price")
    median_slippage_pct: Decimal = Field(description="Median slippage percentage")
    max_slippage_pct: Decimal = Field(description="Maximum observed slippage percentage")
    total_slippage_usdt: Decimal = Field(description="Total slippage cost in USDT")
    slippage_by_exchange: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Average slippage percentage per exchange",
    )
    slippage_by_symbol: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Average slippage percentage per symbol",
    )
    sample_count: int = Field(ge=0, description="Number of executions in the analysis")


class FailureAnalysis(BaseModel):
    """Analysis of failed and aborted executions."""

    total_failures: int = Field(ge=0, description="Total failed executions in the period")
    total_aborted: int = Field(ge=0, description="Total aborted executions in the period")
    failure_rate: Decimal = Field(ge=0, le=100, description="Failure rate as percentage of all executions")
    top_failure_reasons: list[dict[str, int]] = Field(
        default_factory=list,
        description="Most common failure reasons with counts",
    )
    failures_by_exchange: dict[str, int] = Field(
        default_factory=dict,
        description="Failure count per exchange",
    )
    failures_by_symbol: dict[str, int] = Field(
        default_factory=dict,
        description="Failure count per symbol",
    )


# ---------------------------------------------------------------------------
# Composite dashboard
# ---------------------------------------------------------------------------


class AnalyticsDashboard(BaseModel):
    """Aggregation of all analytics views for the dashboard."""

    pnl_summary: PnlSummary = Field(description="Overall PnL summary")
    profit_by_period: list[ProfitByPeriod] = Field(
        default_factory=list, description="PnL broken down by time period"
    )
    profit_by_exchange: list[ProfitByExchange] = Field(
        default_factory=list, description="PnL broken down by exchange pair"
    )
    profit_by_symbol: list[ProfitBySymbol] = Field(
        default_factory=list, description="PnL broken down by symbol"
    )
    profit_by_strategy: list[ProfitByStrategy] = Field(
        default_factory=list, description="PnL broken down by strategy type"
    )
    slippage: SlippageAnalysis = Field(description="Slippage analysis")
    failures: FailureAnalysis = Field(description="Failure analysis")
    recent_executions: list[dict] = Field(
        default_factory=list, description="Recent completed/failed executions"
    )
    top_opportunities: list[dict] = Field(
        default_factory=list, description="Top active opportunities by profit potential"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when this dashboard was generated",
    )
