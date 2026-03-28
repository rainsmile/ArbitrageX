"""Unified exchange error types for structured error handling."""
from __future__ import annotations
from enum import StrEnum


class ExchangeErrorType(StrEnum):
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    PERMISSION_ERROR = "permission_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    EXCHANGE_MAINTENANCE = "exchange_maintenance"
    INVALID_SYMBOL = "invalid_symbol"
    INVALID_PRECISION = "invalid_precision"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    ORDER_REJECTED = "order_rejected"
    ORDER_NOT_FOUND = "order_not_found"
    TIMEOUT_ERROR = "timeout_error"
    TIME_SYNC_ERROR = "time_sync_error"
    UNKNOWN_ERROR = "unknown_error"


class ExchangeError(Exception):
    """Base exception for all exchange-related errors."""
    def __init__(self, error_type: ExchangeErrorType, message: str, *, exchange: str = "", details: dict | None = None):
        self.error_type = error_type
        self.exchange = exchange
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type.value,
            "exchange": self.exchange,
            "message": str(self),
            "details": self.details,
        }

    @property
    def is_retryable(self) -> bool:
        return self.error_type in (
            ExchangeErrorType.NETWORK_ERROR,
            ExchangeErrorType.TIMEOUT_ERROR,
            ExchangeErrorType.RATE_LIMIT_ERROR,
        )

    @property
    def should_circuit_break(self) -> bool:
        return self.error_type in (
            ExchangeErrorType.AUTH_ERROR,
            ExchangeErrorType.PERMISSION_ERROR,
            ExchangeErrorType.EXCHANGE_MAINTENANCE,
            ExchangeErrorType.TIME_SYNC_ERROR,
        )


# Convenience subclasses
class NetworkError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.NETWORK_ERROR, message, **kwargs)

class AuthError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.AUTH_ERROR, message, **kwargs)

class RateLimitError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.RATE_LIMIT_ERROR, message, **kwargs)

class InsufficientBalanceError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.INSUFFICIENT_BALANCE, message, **kwargs)

class OrderRejectedError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.ORDER_REJECTED, message, **kwargs)

class OrderNotFoundError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.ORDER_NOT_FOUND, message, **kwargs)

class InvalidSymbolError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.INVALID_SYMBOL, message, **kwargs)

class TimeSyncError(ExchangeError):
    def __init__(self, message: str, **kwargs):
        super().__init__(ExchangeErrorType.TIME_SYNC_ERROR, message, **kwargs)


def classify_binance_error(http_status: int, error_code: int, message: str) -> ExchangeErrorType:
    """Map Binance error codes to unified error types."""
    if http_status == 429 or http_status == 418:
        return ExchangeErrorType.RATE_LIMIT_ERROR
    if error_code in (-2015, -2014, -1022):
        return ExchangeErrorType.AUTH_ERROR
    if error_code == -1003:
        return ExchangeErrorType.RATE_LIMIT_ERROR
    if error_code == -1021:
        return ExchangeErrorType.TIME_SYNC_ERROR
    if error_code in (-1121, -1100):
        return ExchangeErrorType.INVALID_SYMBOL
    if error_code == -2010:
        return ExchangeErrorType.INSUFFICIENT_BALANCE
    if error_code in (-2011, -2013):
        return ExchangeErrorType.ORDER_NOT_FOUND
    if error_code in (-1013, -1111, -1112):
        return ExchangeErrorType.INVALID_PRECISION
    if error_code == -1015:
        return ExchangeErrorType.RATE_LIMIT_ERROR
    if error_code in (-1001, -1000):
        return ExchangeErrorType.NETWORK_ERROR
    return ExchangeErrorType.UNKNOWN_ERROR


def classify_okx_error(error_code: str, message: str) -> ExchangeErrorType:
    """Map OKX error codes to unified error types."""
    code = error_code
    if code in ("50111", "50113", "50114"):
        return ExchangeErrorType.AUTH_ERROR
    if code in ("50011", "50013"):
        return ExchangeErrorType.RATE_LIMIT_ERROR
    if code in ("51001", "51002"):
        return ExchangeErrorType.INSUFFICIENT_BALANCE
    if code in ("51000", "51014"):
        return ExchangeErrorType.INVALID_SYMBOL
    if code == "51003":
        return ExchangeErrorType.INVALID_PRECISION
    if code in ("51400", "51401"):
        return ExchangeErrorType.ORDER_NOT_FOUND
    if code.startswith("510"):
        return ExchangeErrorType.ORDER_REJECTED
    return ExchangeErrorType.UNKNOWN_ERROR


def classify_bybit_error(ret_code: int, message: str) -> ExchangeErrorType:
    """Map Bybit error codes to unified error types."""
    if ret_code in (10003, 10004, 10005):
        return ExchangeErrorType.AUTH_ERROR
    if ret_code == 10006:
        return ExchangeErrorType.RATE_LIMIT_ERROR
    if ret_code in (110001, 110003):
        return ExchangeErrorType.INSUFFICIENT_BALANCE
    if ret_code in (110007, 110008):
        return ExchangeErrorType.ORDER_NOT_FOUND
    if ret_code in (110044, 110045):
        return ExchangeErrorType.INVALID_PRECISION
    if ret_code in (10001, 10002):
        return ExchangeErrorType.NETWORK_ERROR
    return ExchangeErrorType.UNKNOWN_ERROR
