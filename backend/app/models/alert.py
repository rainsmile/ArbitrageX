"""
Alert model -- user-facing notifications.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class AlertSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"

    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Alert category (e.g. PRICE_SPIKE, EXCHANGE_DOWN)"
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity_enum", create_constraint=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Short alert headline"
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Detailed alert body"
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Component that generated the alert"
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    details_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Structured context for the alert"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_alert_type", "alert_type"),
        Index("ix_alerts_is_read", "is_read"),
        Index("ix_alerts_is_resolved", "is_resolved"),
        Index("ix_alerts_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id!r}, type={self.alert_type!r}, "
            f"severity={self.severity.value}, read={self.is_read})>"
        )
