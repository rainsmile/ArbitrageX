"""
Pure-function utilities used throughout the codebase.

None of these have side-effects or depend on application state.
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from functools import wraps
from typing import Any, Callable, TypeVar

from loguru import logger

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Decimal / precision helpers
# ---------------------------------------------------------------------------

def round_decimal(value: float | Decimal, precision: int = 8) -> Decimal:
    """Round *value* to *precision* decimal places using ROUND_DOWN
    (i.e., truncation — safer for order quantities)."""
    d = Decimal(str(value))
    quantize_str = Decimal(10) ** -precision
    return d.quantize(quantize_str, rounding=ROUND_DOWN)


def truncate_to_precision(value: float, precision: int) -> float:
    """Truncate (not round) a float to the given number of decimal places."""
    factor = 10 ** precision
    return math.trunc(value * factor) / factor


def truncate_price(price: float, tick_size: float) -> float:
    """Truncate *price* to the nearest lower multiple of *tick_size*."""
    if tick_size <= 0:
        return price
    return math.floor(price / tick_size) * tick_size


def truncate_quantity(quantity: float, step_size: float) -> float:
    """Truncate *quantity* to the nearest lower multiple of *step_size*."""
    if step_size <= 0:
        return quantity
    return math.floor(quantity / step_size) * step_size


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns *default* when *denominator* is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def pct_diff(a: float, b: float) -> float:
    """Percentage difference of *a* relative to *b*.

    Returns a positive number when ``a > b``.
    """
    if b == 0:
        return 0.0
    return ((a - b) / b) * 100.0


def spread_pct(ask: float, bid: float) -> float:
    """Calculate the spread percentage: ``(ask - bid) / bid * 100``."""
    return pct_diff(ask, bid)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def now_ms() -> int:
    """Current UTC time as milliseconds since epoch."""
    return int(time.time() * 1000)


def now_utc() -> datetime:
    """Current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


def ms_to_datetime(ms: int) -> datetime:
    """Convert millisecond epoch timestamp to an aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def datetime_to_ms(dt: datetime) -> int:
    """Convert a datetime to millisecond epoch timestamp."""
    return int(dt.timestamp() * 1000)


def elapsed_ms(start_ms: int) -> int:
    """Milliseconds elapsed since *start_ms*."""
    return now_ms() - start_ms


def age_seconds(timestamp_ms: int) -> float:
    """How many seconds ago *timestamp_ms* was."""
    return (now_ms() - timestamp_ms) / 1000.0


# ---------------------------------------------------------------------------
# Retry decorator with exponential backoff
# ---------------------------------------------------------------------------

def retry(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[..., Any] | None = None,
):
    """Decorator that retries an **async** function with exponential backoff.

    Parameters
    ----------
    max_retries:
        Total number of retry attempts (0 = no retries, just the initial call).
    base_delay:
        Initial delay in seconds before the first retry.
    max_delay:
        Upper cap on the delay between retries.
    exponential_base:
        Multiplier applied to the delay after each failure.
    exceptions:
        Tuple of exception types that should trigger a retry.
    on_retry:
        Optional sync callable ``(attempt, exception)`` called before sleeping.

    Example::

        @retry(max_retries=3, base_delay=1.0, exceptions=(ExchangeNetworkError,))
        async def fetch_orderbook(symbol: str):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    logger.warning(
                        "Retry {a}/{m} for {fn} after {d:.2f}s — {exc}",
                        a=attempt + 1,
                        m=max_retries,
                        fn=func.__qualname__,
                        d=delay,
                        exc=str(exc),
                    )
                    if on_retry:
                        on_retry(attempt + 1, exc)
                    await asyncio.sleep(delay)

            # All retries exhausted.
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------

def chunk_list(lst: list[T], size: int) -> list[list[T]]:
    """Split *lst* into chunks of at most *size* elements."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def normalize_symbol(symbol: str) -> str:
    """Ensure a trading pair symbol is in ``BASE/QUOTE`` format.

    Handles common variants: ``BTCUSDT``, ``btc_usdt``, ``BTC-USDT``."""
    s = symbol.upper().replace("_", "").replace("-", "")
    # If already has a slash, just uppercase.
    if "/" in symbol:
        return symbol.upper()
    # Try to split before common quote assets.
    for quote in ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH"):
        if s.endswith(quote):
            base = s[: -len(quote)]
            if base:
                return f"{base}/{quote}"
    return symbol.upper()


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp *value* between *min_val* and *max_val*."""
    return max(min_val, min(value, max_val))
