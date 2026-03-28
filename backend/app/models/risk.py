"""
RiskEvent model -- records of risk rule evaluations.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDType

from app.db.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.execution import ExecutionPlan
    from app.models.opportunity import ArbitrageOpportunity


class RiskSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class RiskEventType(str, enum.Enum):
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"
    ALERT = "ALERT"


class RiskEvent(TimestampMixin, Base):
    __tablename__ = "risk_events"

    rule_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Name of the risk rule that triggered"
    )
    rule_category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Category grouping (e.g. exposure, latency, spread)"
    )
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity, name="risk_severity_enum", create_constraint=True),
        nullable=False,
    )
    event_type: Mapped[RiskEventType] = mapped_column(
        Enum(RiskEventType, name="risk_event_type_enum", create_constraint=True),
        nullable=False,
    )
    opportunity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUIDType(),
        ForeignKey("arbitrage_opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUIDType(),
        ForeignKey("execution_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    details_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Structured details of the risk event"
    )
    threshold_value: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Configured threshold that was breached"
    )
    actual_value: Mapped[Optional[float]] = mapped_column(
        Numeric(28, 12), nullable=True, comment="Actual observed value"
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Human-readable description"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # ---- relationships ----
    opportunity: Mapped[Optional[ArbitrageOpportunity]] = relationship(
        "ArbitrageOpportunity", back_populates="risk_events"
    )
    execution: Mapped[Optional[ExecutionPlan]] = relationship(
        "ExecutionPlan", back_populates="risk_events"
    )

    __table_args__ = (
        Index("ix_risk_events_severity", "severity"),
        Index("ix_risk_events_event_type", "event_type"),
        Index("ix_risk_events_rule_name", "rule_name"),
        Index("ix_risk_events_opportunity", "opportunity_id"),
        Index("ix_risk_events_execution", "execution_id"),
        Index("ix_risk_events_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<RiskEvent(id={self.id!r}, rule={self.rule_name!r}, "
            f"severity={self.severity.value}, type={self.event_type.value})>"
        )
