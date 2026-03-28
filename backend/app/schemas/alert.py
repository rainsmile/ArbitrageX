"""
Alert Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse


class AlertSchema(BaseModel):
    """Read representation of an alert record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Alert unique identifier")
    alert_type: str = Field(description="Alert category (e.g. PRICE_SPIKE, EXCHANGE_DOWN)")
    severity: str = Field(description="Severity level (INFO, WARNING, CRITICAL)")
    title: str = Field(description="Short alert headline")
    message: Optional[str] = Field(default=None, description="Detailed alert body")
    source: Optional[str] = Field(default=None, description="Component that generated the alert")
    is_read: bool = Field(description="Whether the alert has been read")
    is_resolved: bool = Field(description="Whether the alert has been resolved")
    resolved_at: Optional[datetime] = Field(default=None, description="Resolution timestamp")
    details_json: Optional[dict[str, Any]] = Field(default=None, description="Structured context for the alert")
    created_at: datetime = Field(description="Alert creation timestamp")


AlertListResponse = PaginatedResponse[AlertSchema]
