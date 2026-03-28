"""
Custom exception hierarchy for the arbitrage system.

Every exception carries a machine-readable ``code`` (string enum) and an
optional ``details`` dict so that API error responses and internal logging
are consistently structured.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    """Numeric error codes grouped by category.

    1xxx — generic / system
    2xxx — exchange / connectivity
    3xxx — risk management
    4xxx — execution
    5xxx — data / orderbook
    """

    UNKNOWN = 1000
    CONFIGURATION_ERROR = 1001
    DEPENDENCY_UNAVAILABLE = 1002
    TIMEOUT = 1003

    EXCHANGE_ERROR = 2000
    EXCHANGE_AUTH_FAILED = 2001
    EXCHANGE_RATE_LIMITED = 2002
    EXCHANGE_MAINTENANCE = 2003
    EXCHANGE_NETWORK_ERROR = 2004
    EXCHANGE_INVALID_SYMBOL = 2005

    RISK_VIOLATION = 3000
    MAX_ORDER_VALUE_EXCEEDED = 3001
    MAX_DAILY_LOSS_EXCEEDED = 3002
    MAX_CONSECUTIVE_FAILURES = 3003
    MAX_SLIPPAGE_EXCEEDED = 3004
    POSITION_LIMIT_EXCEEDED = 3005

    EXECUTION_ERROR = 4000
    INSUFFICIENT_BALANCE = 4001
    ORDER_REJECTED = 4002
    ORDER_TIMEOUT = 4003
    PARTIAL_FILL = 4004
    EXECUTION_CANCELLED = 4005

    ORDERBOOK_STALE = 5000
    ORDERBOOK_EMPTY = 5001
    PRICE_DEVIATION = 5002
    DATA_INTEGRITY_ERROR = 5003


class BaseAppError(Exception):
    """Base for every application-level exception."""

    code: ErrorCode = ErrorCode.UNKNOWN
    http_status: int = 500

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": True,
            "code": int(self.code),
            "code_name": self.code.name,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code.name}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Exchange errors (2xxx)
# ---------------------------------------------------------------------------

class ExchangeError(BaseAppError):
    """Any error originating from exchange interaction."""

    code = ErrorCode.EXCHANGE_ERROR
    http_status = 502

    def __init__(
        self,
        message: str = "Exchange error",
        *,
        exchange: str = "unknown",
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = {**(details or {}), "exchange": exchange}
        super().__init__(message, code=code, details=details)
        self.exchange = exchange


class ExchangeAuthError(ExchangeError):
    code = ErrorCode.EXCHANGE_AUTH_FAILED
    http_status = 401

    def __init__(self, exchange: str = "unknown", **kwargs: Any) -> None:
        super().__init__(f"Authentication failed for {exchange}", exchange=exchange, **kwargs)


class ExchangeRateLimitError(ExchangeError):
    code = ErrorCode.EXCHANGE_RATE_LIMITED
    http_status = 429

    def __init__(self, exchange: str = "unknown", retry_after: float | None = None, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        if retry_after is not None:
            details["retry_after_s"] = retry_after
        super().__init__(f"Rate limited by {exchange}", exchange=exchange, details=details, **kwargs)
        self.retry_after = retry_after


class ExchangeMaintenanceError(ExchangeError):
    code = ErrorCode.EXCHANGE_MAINTENANCE

    def __init__(self, exchange: str = "unknown", **kwargs: Any) -> None:
        super().__init__(f"{exchange} is under maintenance", exchange=exchange, **kwargs)


class ExchangeNetworkError(ExchangeError):
    code = ErrorCode.EXCHANGE_NETWORK_ERROR

    def __init__(self, exchange: str = "unknown", **kwargs: Any) -> None:
        super().__init__(f"Network error communicating with {exchange}", exchange=exchange, **kwargs)


class ExchangeInvalidSymbolError(ExchangeError):
    code = ErrorCode.EXCHANGE_INVALID_SYMBOL
    http_status = 400

    def __init__(self, symbol: str, exchange: str = "unknown", **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["symbol"] = symbol
        super().__init__(f"Invalid symbol {symbol} on {exchange}", exchange=exchange, details=details, **kwargs)


# ---------------------------------------------------------------------------
# Risk errors (3xxx)
# ---------------------------------------------------------------------------

class RiskViolationError(BaseAppError):
    """A trade was blocked by the risk manager."""

    code = ErrorCode.RISK_VIOLATION
    http_status = 403

    def __init__(
        self,
        message: str = "Risk violation",
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


class MaxOrderValueExceededError(RiskViolationError):
    code = ErrorCode.MAX_ORDER_VALUE_EXCEEDED

    def __init__(self, order_value: float, limit: float, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({"order_value": order_value, "limit": limit})
        super().__init__(
            f"Order value {order_value} exceeds limit {limit}",
            details=details,
            **kwargs,
        )


class MaxDailyLossExceededError(RiskViolationError):
    code = ErrorCode.MAX_DAILY_LOSS_EXCEEDED

    def __init__(self, current_loss: float, limit: float, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({"current_loss": current_loss, "limit": limit})
        super().__init__(
            f"Daily loss {current_loss} exceeds limit {limit}",
            details=details,
            **kwargs,
        )


class MaxSlippageExceededError(RiskViolationError):
    code = ErrorCode.MAX_SLIPPAGE_EXCEEDED

    def __init__(self, slippage_pct: float, limit: float, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({"slippage_pct": slippage_pct, "limit": limit})
        super().__init__(
            f"Slippage {slippage_pct}% exceeds limit {limit}%",
            details=details,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Execution errors (4xxx)
# ---------------------------------------------------------------------------

class ExecutionError(BaseAppError):
    """Something went wrong while executing an arbitrage trade."""

    code = ErrorCode.EXECUTION_ERROR
    http_status = 500

    def __init__(
        self,
        message: str = "Execution error",
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


class InsufficientBalanceError(ExecutionError):
    code = ErrorCode.INSUFFICIENT_BALANCE
    http_status = 400

    def __init__(
        self,
        asset: str,
        required: float,
        available: float,
        exchange: str = "unknown",
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({
            "asset": asset,
            "required": required,
            "available": available,
            "exchange": exchange,
        })
        super().__init__(
            f"Insufficient {asset} on {exchange}: need {required}, have {available}",
            details=details,
            **kwargs,
        )


class OrderRejectedError(ExecutionError):
    code = ErrorCode.ORDER_REJECTED

    def __init__(self, reason: str = "unknown", **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["reason"] = reason
        super().__init__(f"Order rejected: {reason}", details=details, **kwargs)


class OrderTimeoutError(ExecutionError):
    code = ErrorCode.ORDER_TIMEOUT

    def __init__(self, timeout_s: float = 0, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["timeout_s"] = timeout_s
        super().__init__(f"Order not filled within {timeout_s}s", details=details, **kwargs)


class PartialFillError(ExecutionError):
    code = ErrorCode.PARTIAL_FILL

    def __init__(self, filled_pct: float, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["filled_pct"] = filled_pct
        super().__init__(f"Order partially filled ({filled_pct:.1f}%)", details=details, **kwargs)


# ---------------------------------------------------------------------------
# Data / orderbook errors (5xxx)
# ---------------------------------------------------------------------------

class OrderbookStaleError(BaseAppError):
    code = ErrorCode.ORDERBOOK_STALE
    http_status = 503

    def __init__(self, symbol: str, exchange: str, age_s: float, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({"symbol": symbol, "exchange": exchange, "age_s": age_s})
        super().__init__(
            f"Orderbook for {symbol} on {exchange} is stale ({age_s:.1f}s old)",
            details=details,
            **kwargs,
        )


class OrderbookEmptyError(BaseAppError):
    code = ErrorCode.ORDERBOOK_EMPTY
    http_status = 503

    def __init__(self, symbol: str, exchange: str, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({"symbol": symbol, "exchange": exchange})
        super().__init__(f"Empty orderbook for {symbol} on {exchange}", details=details, **kwargs)


class PriceDeviationError(BaseAppError):
    code = ErrorCode.PRICE_DEVIATION
    http_status = 400

    def __init__(self, symbol: str, deviation_pct: float, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details.update({"symbol": symbol, "deviation_pct": deviation_pct})
        super().__init__(
            f"Price deviation of {deviation_pct:.2f}% for {symbol}",
            details=details,
            **kwargs,
        )


class ConfigurationError(BaseAppError):
    code = ErrorCode.CONFIGURATION_ERROR
    http_status = 500

    def __init__(self, message: str = "Configuration error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class DependencyUnavailableError(BaseAppError):
    code = ErrorCode.DEPENDENCY_UNAVAILABLE
    http_status = 503

    def __init__(self, dependency: str, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["dependency"] = dependency
        super().__init__(f"{dependency} is unavailable", details=details, **kwargs)
