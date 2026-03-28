"""
Exchange adapter factory.

Creates, caches and manages the lifecycle of exchange adapter instances.
Uses settings from ``app.core.config`` to wire credentials and flags.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.exchanges.base import BaseExchangeAdapter
from app.exchanges.binance import BinanceAdapter
from app.exchanges.bybit import BybitAdapter
from app.exchanges.mock import MockExchangeAdapter
from app.exchanges.okx import OKXAdapter
from app.exchanges.public_adapter import PublicExchangeAdapter, EXCHANGE_ENDPOINTS

# Exchanges supported by public adapter (no API keys needed)
_PUBLIC_EXCHANGES = set(EXCHANGE_ENDPOINTS.keys())

# Registry of known exchange constructors
_EXCHANGE_CONSTRUCTORS: dict[str, type[BaseExchangeAdapter]] = {
    "binance": BinanceAdapter,
    "okx": OKXAdapter,
    "bybit": BybitAdapter,
    "mock": MockExchangeAdapter,
}


class ExchangeFactory:
    """Singleton-style factory that creates and holds adapter instances.

    Usage::

        factory = ExchangeFactory()
        await factory.initialize_all()      # start configured exchanges
        adapter = factory.get("binance")     # retrieve by name
        await factory.shutdown_all()         # graceful teardown
    """

    def __init__(self) -> None:
        self._adapters: dict[str, BaseExchangeAdapter] = {}

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create(self, name: str, **overrides: Any) -> BaseExchangeAdapter:
        """Create a single adapter by exchange name.

        *name* must be one of: ``binance``, ``okx``, ``bybit``, ``mock``,
        ``mock_<suffix>``.

        Additional keyword arguments are forwarded to the adapter
        constructor, overriding values derived from settings.
        """
        if name in self._adapters:
            return self._adapters[name]

        # Allow "mock_binance", "mock_okx" etc. to create distinct mocks
        base_name = name.split("_")[0] if name.startswith("mock") else name

        if base_name == "binance":
            adapter = BinanceAdapter(
                api_key=overrides.pop("api_key", settings.binance.api_key),
                api_secret=overrides.pop("api_secret", settings.binance.api_secret),
                testnet=overrides.pop("testnet", settings.binance.testnet),
                **overrides,
            )
        elif base_name == "okx":
            adapter = OKXAdapter(
                api_key=overrides.pop("api_key", settings.okx.api_key),
                api_secret=overrides.pop("api_secret", settings.okx.api_secret),
                passphrase=overrides.pop("passphrase", settings.okx.passphrase),
                simulated=overrides.pop("simulated", settings.okx.simulated),
                **overrides,
            )
        elif base_name == "bybit":
            adapter = BybitAdapter(
                api_key=overrides.pop("api_key", settings.bybit.api_key),
                api_secret=overrides.pop("api_secret", settings.bybit.api_secret),
                testnet=overrides.pop("testnet", settings.bybit.testnet),
                **overrides,
            )
        elif base_name == "mock":
            adapter = MockExchangeAdapter(
                name=name,
                **overrides,
            )
        else:
            raise ConfigurationError(f"Unknown exchange: {name!r}")

        self._adapters[name] = adapter
        logger.info("ExchangeFactory: created adapter for {!r}", name)
        return adapter

    def get(self, name: str) -> BaseExchangeAdapter:
        """Retrieve an already-created adapter by name."""
        adapter = self._adapters.get(name)
        if adapter is None:
            raise ConfigurationError(f"Exchange {name!r} not created; call create() first")
        return adapter

    def get_all(self) -> dict[str, BaseExchangeAdapter]:
        """Return all created adapters."""
        return dict(self._adapters)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    async def initialize_all(self) -> None:
        """Call ``initialize()`` on every adapter in the registry."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.initialize()
                logger.info("ExchangeFactory: {} initialised", name)
            except Exception:
                logger.exception("ExchangeFactory: failed to initialise {}", name)

    async def shutdown_all(self) -> None:
        """Call ``shutdown()`` on every adapter (best-effort, never raises)."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.shutdown()
                logger.info("ExchangeFactory: {} shut down", name)
            except Exception:
                logger.exception("ExchangeFactory: error shutting down {}", name)
        self._adapters.clear()

    # ------------------------------------------------------------------
    # Convenience: create from settings
    # ------------------------------------------------------------------

    def create_from_settings(self) -> list[BaseExchangeAdapter]:
        """Create adapters for all exchanges listed in
        ``settings.trading.enabled_exchanges``.

        If ``settings.trading.paper_mode`` is ``True`` and no API keys
        are configured for an exchange, a mock adapter is created
        instead.
        """
        created: list[BaseExchangeAdapter] = []
        for name in settings.trading.enabled_exchanges:
            # Check if we have real credentials
            has_keys = False
            if name == "binance":
                has_keys = bool(settings.binance.api_key)
            elif name == "okx":
                has_keys = bool(settings.okx.api_key)
            elif name == "bybit":
                has_keys = bool(settings.bybit.api_key)

            if has_keys and not settings.trading.paper_mode:
                adapter = self.create(name)
            elif name in _PUBLIC_EXCHANGES:
                # Use public adapter for real market data (no API keys needed)
                logger.info(
                    "ExchangeFactory: using PUBLIC adapter for {} (real market data, read-only)",
                    name,
                )
                adapter = PublicExchangeAdapter(name=name)
                self._adapters[name] = adapter
            else:
                # Fallback to mock for unknown exchanges
                mock_name = f"mock_{name}" if name != "mock" else "mock"
                logger.info(
                    "ExchangeFactory: using mock adapter for {} (paper_mode={}, has_keys={})",
                    name, settings.trading.paper_mode, has_keys,
                )
                adapter = self.create(
                    mock_name,
                    price_offset_pct=_default_offsets.get(name, 0.0),
                )
            created.append(adapter)
        return created


# Default price offsets to create artificial spread between mock exchanges
_default_offsets: dict[str, float] = {
    "binance": 0.0,
    "okx": 0.05,
    "bybit": -0.03,
}
