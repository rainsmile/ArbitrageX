"""
Tests for app.utils.helpers -- pure-function utilities.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.utils.helpers import (
    clamp,
    normalize_symbol,
    now_ms,
    pct_diff,
    retry,
    round_decimal,
    safe_divide,
    spread_pct,
    truncate_to_precision,
)


# ---------------------------------------------------------------------------
# round_decimal
# ---------------------------------------------------------------------------

class TestRoundDecimal:
    def test_default_precision(self):
        result = round_decimal(1.123456789)
        assert result == Decimal("1.12345678")

    def test_precision_2(self):
        result = round_decimal(3.14159, precision=2)
        assert result == Decimal("3.14")

    def test_precision_0(self):
        result = round_decimal(9.9, precision=0)
        assert result == Decimal("9")

    def test_truncates_not_rounds_up(self):
        # 1.999 with precision=2 should truncate to 1.99, not round to 2.00
        result = round_decimal(1.999, precision=2)
        assert result == Decimal("1.99")

    def test_accepts_decimal_input(self):
        result = round_decimal(Decimal("1.23456"), precision=3)
        assert result == Decimal("1.234")

    def test_large_number(self):
        result = round_decimal(60000.123456789, precision=4)
        assert result == Decimal("60000.1234")


# ---------------------------------------------------------------------------
# truncate_to_precision
# ---------------------------------------------------------------------------

class TestTruncateToPrecision:
    def test_basic(self):
        assert truncate_to_precision(1.23456, 3) == 1.234

    def test_no_extra_digits(self):
        assert truncate_to_precision(1.5, 4) == 1.5

    def test_precision_zero(self):
        assert truncate_to_precision(9.87, 0) == 9.0

    def test_truncates_not_rounds(self):
        assert truncate_to_precision(1.999, 2) == 1.99


# ---------------------------------------------------------------------------
# safe_divide
# ---------------------------------------------------------------------------

class TestSafeDivide:
    def test_normal_division(self):
        assert safe_divide(10.0, 2.0) == 5.0

    def test_zero_denominator_returns_default(self):
        assert safe_divide(10.0, 0.0) == 0.0

    def test_zero_denominator_custom_default(self):
        assert safe_divide(10.0, 0.0, default=-1.0) == -1.0

    def test_zero_numerator(self):
        assert safe_divide(0.0, 5.0) == 0.0


# ---------------------------------------------------------------------------
# pct_diff
# ---------------------------------------------------------------------------

class TestPctDiff:
    def test_positive_diff(self):
        # 110 is 10% more than 100
        assert pct_diff(110.0, 100.0) == pytest.approx(10.0)

    def test_negative_diff(self):
        assert pct_diff(90.0, 100.0) == pytest.approx(-10.0)

    def test_zero_base(self):
        assert pct_diff(100.0, 0.0) == 0.0

    def test_equal_values(self):
        assert pct_diff(50.0, 50.0) == 0.0


# ---------------------------------------------------------------------------
# spread_pct
# ---------------------------------------------------------------------------

class TestSpreadPct:
    def test_basic_spread(self):
        # ask=101, bid=100 -> spread = 1%
        assert spread_pct(101.0, 100.0) == pytest.approx(1.0)

    def test_zero_spread(self):
        assert spread_pct(100.0, 100.0) == 0.0

    def test_negative_spread(self):
        # ask < bid (crossed book)
        result = spread_pct(99.0, 100.0)
        assert result == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# normalize_symbol
# ---------------------------------------------------------------------------

class TestNormalizeSymbol:
    def test_btcusdt(self):
        assert normalize_symbol("BTCUSDT") == "BTC/USDT"

    def test_btc_usdt_dash(self):
        assert normalize_symbol("BTC-USDT") == "BTC/USDT"

    def test_btc_usdt_underscore(self):
        assert normalize_symbol("btc_usdt") == "BTC/USDT"

    def test_already_normalized(self):
        assert normalize_symbol("BTC/USDT") == "BTC/USDT"

    def test_ethusdt(self):
        assert normalize_symbol("ETHUSDT") == "ETH/USDT"

    def test_solusdt(self):
        assert normalize_symbol("SOLUSDT") == "SOL/USDT"

    def test_ethbtc(self):
        assert normalize_symbol("ETHBTC") == "ETH/BTC"

    def test_lowercase(self):
        assert normalize_symbol("btcusdt") == "BTC/USDT"


# ---------------------------------------------------------------------------
# clamp
# ---------------------------------------------------------------------------

class TestClamp:
    def test_value_within_range(self):
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_value_below_min(self):
        assert clamp(-1.0, 0.0, 10.0) == 0.0

    def test_value_above_max(self):
        assert clamp(15.0, 0.0, 10.0) == 10.0

    def test_value_at_min(self):
        assert clamp(0.0, 0.0, 10.0) == 0.0

    def test_value_at_max(self):
        assert clamp(10.0, 0.0, 10.0) == 10.0


# ---------------------------------------------------------------------------
# now_ms
# ---------------------------------------------------------------------------

class TestNowMs:
    def test_returns_int(self):
        result = now_ms()
        assert isinstance(result, int)

    def test_reasonable_range(self):
        result = now_ms()
        # Should be after 2024-01-01 in ms
        assert result > 1_704_067_200_000


# ---------------------------------------------------------------------------
# retry decorator
# ---------------------------------------------------------------------------

class TestRetryDecorator:
    async def test_succeeds_first_try(self):
        call_count = 0

        @retry(max_retries=3, base_delay=0.01)
        async def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await success()
        assert result == "ok"
        assert call_count == 1

    async def test_fails_then_succeeds(self):
        call_count = 0

        @retry(max_retries=3, base_delay=0.01)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("temporary failure")
            return "recovered"

        result = await flaky()
        assert result == "recovered"
        assert call_count == 3

    async def test_exhausts_retries_and_raises(self):
        @retry(max_retries=2, base_delay=0.01)
        async def always_fail():
            raise ValueError("permanent failure")

        with pytest.raises(ValueError, match="permanent failure"):
            await always_fail()

    async def test_on_retry_callback(self):
        attempts_seen: list[int] = []

        def on_retry(attempt: int, exc: BaseException):
            attempts_seen.append(attempt)

        call_count = 0

        @retry(max_retries=2, base_delay=0.01, on_retry=on_retry)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "ok"

        await flaky()
        assert attempts_seen == [1]
