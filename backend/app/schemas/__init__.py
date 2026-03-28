"""
Pydantic v2 schemas for the arbitrage system API.

Import all public schemas here for convenient access::

    from app.schemas import ArbitrageOpportunitySchema, Ticker, ...
"""

# -- common ----------------------------------------------------------------
from app.schemas.common import (
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
    StatusResponse,
    TimeRange,
)

# -- exchange --------------------------------------------------------------
from app.schemas.exchange import ExchangeInfo, ExchangeStatus, SymbolInfo

# -- market ----------------------------------------------------------------
from app.schemas.market import Orderbook, OrderbookLevel, SpreadInfo, Ticker

# -- opportunity -----------------------------------------------------------
from app.schemas.opportunity import (
    ArbitrageOpportunitySchema,
    OpportunityFilter,
    OpportunityListResponse,
)

# -- execution -------------------------------------------------------------
from app.schemas.execution import (
    ExecutionCreate,
    ExecutionLegSchema,
    ExecutionListResponse,
    ExecutionPlanSchema,
)

# -- order -----------------------------------------------------------------
from app.schemas.order import OrderListResponse, OrderSchema

# -- risk ------------------------------------------------------------------
from app.schemas.risk import (
    RiskEventSchema,
    RiskExposure,
    RiskRuleSchema,
    RiskSummary,
)

# -- inventory -------------------------------------------------------------
from app.schemas.inventory import (
    AssetSummary,
    BalanceSchema,
    ExchangeAllocation,
    InventorySummary,
    RebalanceSuggestionSchema,
)

# -- analytics -------------------------------------------------------------
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

# -- strategy --------------------------------------------------------------
from app.schemas.strategy import (
    StrategyConfigSchema,
    StrategyConfigUpdate,
    StrategyListResponse,
)

# -- alert -----------------------------------------------------------------
from app.schemas.alert import AlertListResponse, AlertSchema

# -- system ----------------------------------------------------------------
from app.schemas.system import (
    SystemEventSchema,
    SystemHealth,
    SystemMetrics,
    WsStatus,
)

# -- websocket -------------------------------------------------------------
from app.schemas.ws import (
    WsAlertUpdate,
    WsExecutionUpdate,
    WsMarketUpdate,
    WsMessage,
    WsOpportunityUpdate,
)

__all__ = [
    # common
    "PaginatedResponse",
    "StatusResponse",
    "ErrorDetail",
    "ErrorResponse",
    "TimeRange",
    # exchange
    "ExchangeInfo",
    "ExchangeStatus",
    "SymbolInfo",
    # market
    "Ticker",
    "OrderbookLevel",
    "Orderbook",
    "SpreadInfo",
    # opportunity
    "ArbitrageOpportunitySchema",
    "OpportunityListResponse",
    "OpportunityFilter",
    # execution
    "ExecutionPlanSchema",
    "ExecutionLegSchema",
    "ExecutionListResponse",
    "ExecutionCreate",
    # order
    "OrderSchema",
    "OrderListResponse",
    # risk
    "RiskRuleSchema",
    "RiskEventSchema",
    "RiskExposure",
    "RiskSummary",
    # inventory
    "BalanceSchema",
    "ExchangeAllocation",
    "AssetSummary",
    "InventorySummary",
    "RebalanceSuggestionSchema",
    # analytics
    "PnlSummary",
    "ProfitByPeriod",
    "ProfitByExchange",
    "ProfitBySymbol",
    "ProfitByStrategy",
    "SlippageAnalysis",
    "FailureAnalysis",
    "AnalyticsDashboard",
    # strategy
    "StrategyConfigSchema",
    "StrategyConfigUpdate",
    "StrategyListResponse",
    # alert
    "AlertSchema",
    "AlertListResponse",
    # system
    "SystemHealth",
    "SystemMetrics",
    "WsStatus",
    "SystemEventSchema",
    # websocket
    "WsMessage",
    "WsMarketUpdate",
    "WsOpportunityUpdate",
    "WsExecutionUpdate",
    "WsAlertUpdate",
]
