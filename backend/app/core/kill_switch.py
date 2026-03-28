"""Kill switch and circuit breaker for live trading safety."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any
from loguru import logger


@dataclass
class CircuitBreakerState:
    """State for a single circuit breaker."""
    scope: str           # "global", "exchange:binance", "strategy:cross_exchange", "symbol:BTC/USDT"
    is_open: bool = False
    opened_at: float = 0.0
    reason: str = ""
    failure_count: int = 0
    failure_threshold: int = 5
    auto_reset_after_s: float = 300.0  # 5 minutes
    last_failure_at: float = 0.0

    @property
    def should_auto_reset(self) -> bool:
        if not self.is_open or self.auto_reset_after_s <= 0:
            return False
        return (time.time() - self.opened_at) > self.auto_reset_after_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "is_open": self.is_open,
            "opened_at": self.opened_at,
            "reason": self.reason,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "auto_reset_after_s": self.auto_reset_after_s,
            "time_until_reset_s": max(0, self.auto_reset_after_s - (time.time() - self.opened_at)) if self.is_open else 0,
        }


class KillSwitch:
    """Global kill switch for emergency trading halt."""

    def __init__(self) -> None:
        self._active = False
        self._activated_at: float = 0.0
        self._activated_by: str = ""
        self._reason: str = ""
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}

    # -- Global kill switch --

    @property
    def is_active(self) -> bool:
        return self._active

    def activate(self, reason: str = "", activated_by: str = "system") -> None:
        self._active = True
        self._activated_at = time.time()
        self._activated_by = activated_by
        self._reason = reason
        logger.critical("KILL SWITCH ACTIVATED by={} reason={}", activated_by, reason)

    def release(self, released_by: str = "system") -> None:
        self._active = False
        logger.warning("Kill switch released by={}", released_by)

    def get_status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "activated_at": self._activated_at,
            "activated_by": self._activated_by,
            "reason": self._reason,
        }

    # -- Circuit breakers --

    def get_or_create_breaker(self, scope: str, threshold: int = 5, auto_reset_s: float = 300.0) -> CircuitBreakerState:
        if scope not in self._circuit_breakers:
            self._circuit_breakers[scope] = CircuitBreakerState(
                scope=scope, failure_threshold=threshold, auto_reset_after_s=auto_reset_s,
            )
        return self._circuit_breakers[scope]

    def record_failure(self, scope: str, reason: str = "") -> bool:
        """Record a failure. Returns True if circuit breaker tripped."""
        cb = self.get_or_create_breaker(scope)
        cb.failure_count += 1
        cb.last_failure_at = time.time()
        if cb.failure_count >= cb.failure_threshold and not cb.is_open:
            cb.is_open = True
            cb.opened_at = time.time()
            cb.reason = reason or f"Failure threshold reached ({cb.failure_count}/{cb.failure_threshold})"
            logger.warning("Circuit breaker OPEN: scope={} reason={}", scope, cb.reason)
            return True
        return False

    def record_success(self, scope: str) -> None:
        cb = self._circuit_breakers.get(scope)
        if cb:
            cb.failure_count = 0
            if cb.is_open and cb.should_auto_reset:
                cb.is_open = False
                logger.info("Circuit breaker auto-reset: scope={}", scope)

    def is_circuit_open(self, scope: str) -> bool:
        cb = self._circuit_breakers.get(scope)
        if not cb:
            return False
        # Check auto-reset
        if cb.is_open and cb.should_auto_reset:
            cb.is_open = False
            cb.failure_count = 0
            logger.info("Circuit breaker auto-reset: scope={}", scope)
            return False
        return cb.is_open

    def reset_breaker(self, scope: str) -> bool:
        cb = self._circuit_breakers.get(scope)
        if cb:
            cb.is_open = False
            cb.failure_count = 0
            cb.reason = ""
            logger.info("Circuit breaker manually reset: scope={}", scope)
            return True
        return False

    def get_all_breakers(self) -> list[dict[str, Any]]:
        # Auto-check resets
        for cb in self._circuit_breakers.values():
            if cb.is_open and cb.should_auto_reset:
                cb.is_open = False
                cb.failure_count = 0
        return [cb.to_dict() for cb in self._circuit_breakers.values()]

    def get_open_breakers(self) -> list[dict[str, Any]]:
        return [cb.to_dict() for cb in self._circuit_breakers.values() if cb.is_open]
