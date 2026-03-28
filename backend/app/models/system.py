"""
System models -- operational events and audit trail.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SystemSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class SystemEvent(TimestampMixin, Base):
    __tablename__ = "system_events"

    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Event category (e.g. STARTUP, SHUTDOWN, ERROR)"
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Component that emitted the event"
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Human-readable description"
    )
    details_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Structured event data"
    )
    severity: Mapped[SystemSeverity] = mapped_column(
        Enum(SystemSeverity, name="system_severity_enum", create_constraint=True),
        default=SystemSeverity.INFO,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_system_events_event_type", "event_type"),
        Index("ix_system_events_severity", "severity"),
        Index("ix_system_events_source", "source"),
        Index("ix_system_events_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SystemEvent(id={self.id!r}, type={self.event_type!r}, "
            f"severity={self.severity.value})>"
        )


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Action performed (e.g. CREATE, UPDATE, DELETE)"
    )
    actor: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="User or service that performed the action"
    )
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Type of resource affected"
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="ID of the resource affected"
    )
    details_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Before/after snapshot or relevant context"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True, comment="Client IP address (supports IPv6)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_actor", "actor"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id!r}, action={self.action!r}, "
            f"actor={self.actor!r}, resource={self.resource_type}:{self.resource_id})>"
        )
