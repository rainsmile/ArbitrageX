"""
Common Pydantic schemas shared across the application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic paginated response
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T] = Field(description="Page of result items")
    total: int = Field(ge=0, description="Total number of records matching the query")
    page: int = Field(ge=1, description="Current page number (1-based)")
    page_size: int = Field(ge=1, le=500, description="Number of items per page")
    total_pages: int = Field(ge=0, description="Total number of pages")


# ---------------------------------------------------------------------------
# Status / error envelopes
# ---------------------------------------------------------------------------


class StatusResponse(BaseModel):
    """Simple status acknowledgement."""

    status: str = Field(description="Status indicator (e.g. 'ok', 'error')")
    message: str = Field(default="", description="Human-readable message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Server timestamp of the response",
    )


class ErrorDetail(BaseModel):
    """Single error detail entry."""

    field: Optional[str] = Field(default=None, description="Field that caused the error, if applicable")
    message: str = Field(description="Human-readable error description")
    code: Optional[str] = Field(default=None, description="Machine-readable error code")


class ErrorResponse(BaseModel):
    """Structured error response returned to clients."""

    status: str = Field(default="error", description="Always 'error'")
    message: str = Field(description="Top-level error message")
    errors: list[ErrorDetail] = Field(default_factory=list, description="Detailed error entries")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Server timestamp of the error",
    )


# ---------------------------------------------------------------------------
# Time range filter
# ---------------------------------------------------------------------------


class TimeRange(BaseModel):
    """Reusable time-range filter for query endpoints."""

    start: Optional[datetime] = Field(default=None, description="Inclusive start of the time range (UTC)")
    end: Optional[datetime] = Field(default=None, description="Inclusive end of the time range (UTC)")
