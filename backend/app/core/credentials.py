"""Secure credential management for exchange API keys."""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Any
from loguru import logger


def _mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret string, showing only first/last chars."""
    if not value:
        return "(empty)"
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return value[:visible_chars] + "*" * (len(value) - visible_chars * 2) + value[-visible_chars:]


@dataclass
class ExchangeCredential:
    """Secure container for exchange API credentials."""
    exchange: str
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""  # OKX requires this
    label: str = ""
    is_read_only: bool = False
    is_trading_enabled: bool = False
    source: str = "env"  # env | file | vault

    @property
    def has_keys(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def masked_key(self) -> str:
        return _mask_secret(self.api_key)

    @property
    def masked_secret(self) -> str:
        return _mask_secret(self.api_secret)

    def to_safe_dict(self) -> dict[str, Any]:
        """Return dict safe for logging/API responses. NEVER exposes secrets."""
        return {
            "exchange": self.exchange,
            "api_key": self.masked_key,
            "has_secret": bool(self.api_secret),
            "has_passphrase": bool(self.passphrase),
            "label": self.label,
            "is_read_only": self.is_read_only,
            "is_trading_enabled": self.is_trading_enabled,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return f"ExchangeCredential(exchange={self.exchange!r}, key={self.masked_key})"

    # Prevent accidental serialization of secrets
    def __str__(self) -> str:
        return f"Credential({self.exchange}, key={self.masked_key})"


class CredentialManager:
    """Loads and validates exchange credentials from various sources."""

    def __init__(self) -> None:
        self._credentials: dict[str, ExchangeCredential] = {}

    def load_from_env(self) -> None:
        """Load credentials from environment variables."""
        exchanges = {
            "binance": ("BINANCE_API_KEY", "BINANCE_API_SECRET", ""),
            "okx": ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"),
            "bybit": ("BYBIT_API_KEY", "BYBIT_API_SECRET", ""),
        }
        for name, (key_var, secret_var, pass_var) in exchanges.items():
            api_key = os.getenv(key_var, "")
            api_secret = os.getenv(secret_var, "")
            passphrase = os.getenv(pass_var, "") if pass_var else ""

            cred = ExchangeCredential(
                exchange=name,
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                source="env",
            )
            self._credentials[name] = cred
            if cred.has_keys:
                logger.info("Credential loaded for {}: key={}", name, cred.masked_key)
            else:
                logger.debug("No API key configured for {}", name)

    def get(self, exchange: str) -> ExchangeCredential | None:
        return self._credentials.get(exchange)

    def get_all(self) -> dict[str, ExchangeCredential]:
        return dict(self._credentials)

    def has_valid_keys(self, exchange: str) -> bool:
        cred = self._credentials.get(exchange)
        return cred is not None and cred.has_keys

    def get_status_summary(self) -> list[dict[str, Any]]:
        """Return safe summary of all credentials for API/dashboard."""
        return [cred.to_safe_dict() for cred in self._credentials.values()]

    async def validate_connectivity(self, exchange: str, adapter: Any) -> dict[str, Any]:
        """Test if credential can connect to exchange. Returns validation result."""
        cred = self._credentials.get(exchange)
        if not cred or not cred.has_keys:
            return {"exchange": exchange, "connected": False, "reason": "no_api_keys"}
        try:
            info = await adapter.get_exchange_info()
            # Try to get balance to test authenticated access
            can_read = False
            try:
                await adapter.get_balance()
                can_read = True
            except Exception:
                pass

            cred.is_read_only = can_read and not cred.is_trading_enabled
            return {
                "exchange": exchange,
                "connected": True,
                "server_time": str(info.server_time) if info.server_time else None,
                "can_read_account": can_read,
                "api_key": cred.masked_key,
            }
        except Exception as e:
            return {"exchange": exchange, "connected": False, "reason": str(e)[:200]}
