"""
Risk management endpoints -- rules, events, and exposure.

Router prefix: /api/risk
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.models.balance import Balance
from app.models.exchange import Exchange
from app.models.risk import RiskEvent, RiskEventType, RiskSeverity
from app.schemas.risk import RiskEventSchema, RiskExposure, RiskRuleSchema
from app.services.scanner import OpportunityCandidate

router = APIRouter(prefix="/api/risk", tags=["risk"])


# ---------------------------------------------------------------------------
# Risk rule update request
# ---------------------------------------------------------------------------


class RiskRuleUpdate(BaseModel):
    """Payload to update a risk rule."""

    enabled: Optional[bool] = Field(default=None, description="Enable or disable the rule")
    threshold: Optional[Decimal] = Field(default=None, ge=0, description="New threshold value")


# ---------------------------------------------------------------------------
# In-memory risk rules (persisted via settings, managed in-memory here)
# ---------------------------------------------------------------------------

_RISK_RULES: dict[str, RiskRuleSchema] = {
    "max_order_value": RiskRuleSchema(
        name="max_order_value",
        category="exposure",
        enabled=True,
        threshold=Decimal(str(settings.risk.max_order_value_usdt)),
        description="Maximum single order value in USDT",
    ),
    "max_position_value": RiskRuleSchema(
        name="max_position_value",
        category="exposure",
        enabled=True,
        threshold=Decimal(str(settings.risk.max_position_value_usdt)),
        description="Maximum total open position value in USDT",
    ),
    "max_daily_loss": RiskRuleSchema(
        name="max_daily_loss",
        category="loss",
        enabled=True,
        threshold=Decimal(str(settings.risk.max_daily_loss_usdt)),
        description="Stop trading after this daily loss in USDT",
    ),
    "max_consecutive_failures": RiskRuleSchema(
        name="max_consecutive_failures",
        category="execution",
        enabled=True,
        threshold=Decimal(str(settings.risk.max_consecutive_failures)),
        description="Pause after N consecutive failed executions",
    ),
    "max_slippage": RiskRuleSchema(
        name="max_slippage",
        category="spread",
        enabled=True,
        threshold=Decimal(str(settings.risk.max_slippage_pct)),
        description="Maximum tolerated slippage percentage",
    ),
    "min_profit_threshold": RiskRuleSchema(
        name="min_profit_threshold",
        category="spread",
        enabled=True,
        threshold=Decimal(str(settings.risk.min_profit_threshold_pct)),
        description="Minimum spread percentage to consider an opportunity",
    ),
    "min_profit_absolute": RiskRuleSchema(
        name="min_profit_absolute",
        category="spread",
        enabled=True,
        threshold=Decimal(str(settings.risk.min_profit_threshold_usdt)),
        description="Minimum absolute profit in USDT to execute",
    ),
    "max_open_orders": RiskRuleSchema(
        name="max_open_orders",
        category="execution",
        enabled=True,
        threshold=Decimal(str(settings.risk.max_open_orders)),
        description="Maximum number of open orders at any time",
    ),
}


@router.get(
    "/rules",
    response_model=list[RiskRuleSchema],
    summary="List all risk rules",
)
async def list_risk_rules() -> list[RiskRuleSchema]:
    """Return all risk rules with their current settings."""
    return list(_RISK_RULES.values())


@router.put(
    "/rules/{rule_name}",
    response_model=RiskRuleSchema,
    summary="Update a risk rule",
)
async def update_risk_rule(
    rule_name: str,
    payload: RiskRuleUpdate,
) -> RiskRuleSchema:
    """Update a risk rule by name. Can enable/disable or change threshold."""

    rule = _RISK_RULES.get(rule_name)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Risk rule '{rule_name}' not found")

    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.threshold is not None:
        rule.threshold = payload.threshold

    _RISK_RULES[rule_name] = rule
    return rule


@router.get(
    "/events",
    response_model=list[RiskEventSchema],
    summary="List risk events",
)
async def list_risk_events(
    severity: Optional[str] = Query(None, description="Filter by severity (INFO, WARNING, CRITICAL)"),
    rule_name: Optional[str] = Query(None, description="Filter by rule name"),
    start_time: Optional[datetime] = Query(None, description="Start of time range (ISO8601)"),
    end_time: Optional[datetime] = Query(None, description="End of time range (ISO8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    db: AsyncSession = Depends(get_db),
) -> list[RiskEventSchema]:
    """Return risk events with optional filters."""

    try:
        query = select(RiskEvent)

        if severity:
            query = query.where(RiskEvent.severity == severity)
        if rule_name:
            query = query.where(RiskEvent.rule_name == rule_name)
        if start_time:
            query = query.where(RiskEvent.created_at >= start_time)
        if end_time:
            query = query.where(RiskEvent.created_at <= end_time)

        query = query.order_by(RiskEvent.created_at.desc()).limit(limit)

        result = await db.execute(query)
        events = result.scalars().all()
        return [RiskEventSchema.model_validate(e) for e in events]
    except Exception as exc:
        logger.debug("Failed to query risk events: {}", exc)
        return []


@router.get(
    "/exposure",
    response_model=list[RiskExposure],
    summary="Current risk exposure per exchange/asset",
)
async def get_risk_exposure(
    db: AsyncSession = Depends(get_db),
) -> list[RiskExposure]:
    """Return current risk exposure per exchange/asset combination."""

    try:
        result = await db.execute(
            select(Balance, Exchange.name)
            .join(Exchange, Balance.exchange_id == Exchange.id)
            .where(Balance.total > 0)
            .order_by(Exchange.name, Balance.asset)
        )
        rows = result.all()

        # Calculate total USD value
        total_usd = Decimal(0)
        exposures_raw: list[tuple[str, str, Decimal, Decimal | None]] = []
        for balance, exchange_name in rows:
            usd_val = Decimal(str(balance.usd_value)) if balance.usd_value else Decimal(0)
            total_usd += usd_val
            exposures_raw.append((exchange_name, balance.asset, Decimal(str(balance.total)), usd_val))

        exposures: list[RiskExposure] = []
        for exchange_name, asset, amount, usd_val in exposures_raw:
            pct = (usd_val / total_usd * 100) if total_usd > 0 else Decimal(0)
            exposures.append(
                RiskExposure(
                    exchange=exchange_name,
                    asset=asset,
                    amount=amount,
                    usd_value=usd_val,
                    pct_of_total=min(pct, Decimal(100)),
                )
            )

        if exposures:
            return exposures
    except Exception as exc:
        logger.debug("Failed to query exposure: {}", exc)

    return []


# ---------------------------------------------------------------------------
# Risk check via coordinator's risk engine
# ---------------------------------------------------------------------------


class RiskCheckRequest(BaseModel):
    symbol: str = Field(..., description="Trading pair, e.g. BTC/USDT")
    buy_exchange: str = Field(..., description="Exchange to buy on")
    sell_exchange: str = Field(..., description="Exchange to sell on")
    buy_price: float = Field(..., gt=0, description="Buy price")
    sell_price: float = Field(..., gt=0, description="Sell price")
    quantity: float = Field(..., gt=0, description="Trade quantity")
    estimated_profit_pct: float = Field(default=0.0, description="Estimated profit percentage")


@router.post(
    "/check",
    summary="Run risk check on an opportunity",
)
async def run_risk_check(
    payload: RiskCheckRequest,
    request: Request,
):
    """Create a mock OpportunityCandidate from the provided parameters and
    run it through the risk engine's evaluate method."""

    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ExecutionCoordinator not available")

    risk_engine = coordinator._risk_engine

    spread_pct = (
        (payload.sell_price - payload.buy_price) / payload.buy_price * 100.0
        if payload.buy_price > 0
        else 0.0
    )

    opp = OpportunityCandidate(
        strategy_type="CROSS_EXCHANGE",
        symbol=payload.symbol,
        symbols=[payload.symbol],
        exchanges=[payload.buy_exchange, payload.sell_exchange],
        buy_exchange=payload.buy_exchange,
        sell_exchange=payload.sell_exchange,
        buy_price=payload.buy_price,
        sell_price=payload.sell_price,
        spread_pct=spread_pct,
        theoretical_profit_pct=spread_pct,
        estimated_net_profit_pct=payload.estimated_profit_pct,
        executable_quantity=payload.quantity,
        executable_value_usdt=payload.quantity * payload.buy_price,
    )

    from app.services.risk_engine import RiskContext
    decision = await risk_engine.evaluate(opp, context=RiskContext())

    return {
        "approved": decision.approved,
        "timestamp": decision.timestamp,
        "violations": [
            {"rule_name": v.rule_name, "reason": v.reason, "details": v.details}
            for v in decision.violations
        ],
        "results": [
            {"rule_name": r.rule_name, "passed": r.passed, "reason": r.reason, "details": r.details}
            for r in decision.results
        ],
    }
