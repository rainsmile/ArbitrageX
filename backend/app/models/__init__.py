"""
SQLAlchemy ORM models for the arbitrage system.

Import all models here so that ``Base.metadata`` discovers every table
when Alembic (or ``init_db``) inspects the registry.
"""

from app.models.base import TimestampMixin  # noqa: F401

from app.models.exchange import Exchange  # noqa: F401
from app.models.symbol import ExchangeSymbol  # noqa: F401
from app.models.balance import Balance  # noqa: F401

from app.models.market import MarketTick, OrderbookSnapshot  # noqa: F401

from app.models.opportunity import (  # noqa: F401
    ArbitrageOpportunity,
    OpportunityStatus,
    StrategyType,
)

from app.models.execution import (  # noqa: F401
    ExecutionLeg,
    ExecutionMode,
    ExecutionPlan,
    ExecutionPlanStatus,
    LegSide,
    LegStatus,
)

from app.models.order import (  # noqa: F401
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)

from app.models.risk import (  # noqa: F401
    RiskEvent,
    RiskEventType,
    RiskSeverity,
)

from app.models.alert import Alert, AlertSeverity  # noqa: F401

from app.models.strategy import StrategyConfig  # noqa: F401

from app.models.analytics import (  # noqa: F401
    PnlRecord,
    RebalanceStatus,
    RebalanceSuggestion,
)

from app.models.system import AuditLog, SystemEvent, SystemSeverity  # noqa: F401

__all__ = [
    # base
    "TimestampMixin",
    # exchange
    "Exchange",
    "ExchangeSymbol",
    "Balance",
    # market data
    "MarketTick",
    "OrderbookSnapshot",
    # opportunity
    "ArbitrageOpportunity",
    "OpportunityStatus",
    "StrategyType",
    # execution
    "ExecutionPlan",
    "ExecutionPlanStatus",
    "ExecutionLeg",
    "ExecutionMode",
    "LegSide",
    "LegStatus",
    # orders
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    # risk
    "RiskEvent",
    "RiskEventType",
    "RiskSeverity",
    # alerts
    "Alert",
    "AlertSeverity",
    # strategy
    "StrategyConfig",
    # analytics
    "PnlRecord",
    "RebalanceSuggestion",
    "RebalanceStatus",
    # system
    "SystemEvent",
    "SystemSeverity",
    "AuditLog",
]
