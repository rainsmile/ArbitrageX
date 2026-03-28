"""
Application configuration using Pydantic Settings.

All values are read from environment variables with sensible defaults
for local development. Production deployments should set env vars or
use a .env file.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    url: str = Field(
        default="mysql+aiomysql://myuser:YourPassword123!@127.0.0.1:3306/mydb?charset=utf8mb4",
        description="Async SQLAlchemy database URL",
    )
    pool_size: int = Field(default=20, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_recycle: int = Field(default=3600, description="Seconds before recycling a connection")
    echo: bool = Field(default=False, description="Echo SQL statements for debugging")


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379/0")
    max_connections: int = Field(default=50, ge=1)
    decode_responses: bool = Field(default=True)
    socket_timeout: float = Field(default=5.0)
    socket_connect_timeout: float = Field(default=5.0)


class ExchangeKeySettings(BaseSettings):
    """API credentials for a single exchange. All optional so the system can
    run in paper-mode or with only a subset of exchanges configured."""

    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    passphrase: str = Field(default="")


class BinanceSettings(ExchangeKeySettings):
    model_config = SettingsConfigDict(env_prefix="BINANCE_")
    testnet: bool = Field(default=False)


class OkxSettings(ExchangeKeySettings):
    model_config = SettingsConfigDict(env_prefix="OKX_")
    simulated: bool = Field(default=False)


class BybitSettings(ExchangeKeySettings):
    model_config = SettingsConfigDict(env_prefix="BYBIT_")
    testnet: bool = Field(default=False)


class TradingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_")

    paper_mode: bool = Field(default=True, description="Paper trading mode — no real orders")
    enabled_exchanges: list[str] = Field(
        default=["binance", "okx", "bybit", "kraken", "kucoin", "gate", "htx", "bitget", "mexc"],
        description="Exchanges to activate (top global exchanges)",
    )


class RiskSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISK_")

    max_order_value_usdt: float = Field(default=10_000.0, description="Max single order value in USDT")
    max_position_value_usdt: float = Field(default=50_000.0, description="Max total open position value")
    max_daily_loss_usdt: float = Field(default=500.0, description="Stop trading after this daily loss")
    max_consecutive_failures: int = Field(default=5, description="Pause after N consecutive failed executions")
    max_slippage_pct: float = Field(default=0.15, description="Max tolerated slippage percent")
    min_profit_threshold_pct: float = Field(default=0.05, description="Min spread pct to consider an opportunity")
    min_profit_threshold_usdt: float = Field(default=1.0, description="Min absolute profit to execute")
    max_open_orders: int = Field(default=10)
    cooldown_after_failure_s: int = Field(default=30)


class StrategySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STRATEGY_")

    enabled_pairs: list[str] = Field(
        default=[
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "XRP/USDT",
            "DOGE/USDT",
            "ADA/USDT",
            "AVAX/USDT",
            "LINK/USDT",
            "DOT/USDT",
            "POL/USDT",
        ],
    )
    scan_interval_ms: int = Field(default=500, description="How often to scan for opportunities (ms)")
    min_depth_usdt: float = Field(default=500.0, description="Minimum orderbook depth in USDT to consider")
    orderbook_depth_levels: int = Field(default=10, description="Levels of orderbook to fetch")
    opportunity_ttl_s: int = Field(default=5, description="Seconds before an opportunity is considered stale")
    execution_timeout_s: int = Field(default=10, description="Max seconds to wait for order fill")


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = Field(default="INFO")
    json_format: bool = Field(default=True, description="Output structured JSON logs")
    dir: str = Field(default="logs")
    app_file: str = Field(default="app.log")
    trade_file: str = Field(default="trades.log")
    error_file: str = Field(default="errors.log")
    rotation: str = Field(default="100 MB")
    retention: str = Field(default="30 days")
    compression: str = Field(default="gz")


class AlertSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALERT_")

    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    email_smtp_host: str = Field(default="")
    email_smtp_port: int = Field(default=587)
    email_from: str = Field(default="")
    email_to: str = Field(default="")
    email_password: str = Field(default="")
    enabled_channels: list[str] = Field(default=["log"], description="log | telegram | email")


class LiveTradingSettings(BaseSettings):
    """Settings specific to live/real trading safety."""
    model_config = SettingsConfigDict(env_prefix="LIVE_")

    enabled: bool = False
    enable_live_small: bool = False
    trading_mode: str = "paper"  # mock, read_only, paper, simulation, live_small, live

    # Global switches
    allow_auto_execution: bool = True
    allow_real_cancellation: bool = True
    allow_hedging: bool = True
    require_manual_confirmation: bool = False
    paper_trade_size_usdt: float = 1000.0  # Starting amount for paper execution

    # Whitelists (empty = allow all configured)
    exchange_whitelist: list[str] = []
    symbol_whitelist: list[str] = []
    strategy_whitelist: list[str] = []

    # Live-small limits
    live_small_max_single_usdt: float = 50.0
    live_small_max_daily_usdt: float = 500.0

    # Live limits
    live_max_single_usdt: float = 5000.0
    live_max_daily_per_exchange_usdt: float = 50000.0
    live_max_daily_per_symbol_usdt: float = 20000.0
    live_max_daily_total_usdt: float = 100000.0
    live_max_daily_loss_usdt: float = 200.0
    live_max_open_exposure_usdt: float = 30000.0

    # Price deviation protection
    max_price_deviation_pct: float = 0.5  # Max 0.5% deviation from mid price
    max_price_staleness_s: float = 3.0    # Max 3 seconds data age for live orders

    # Circuit breaker
    circuit_breaker_threshold: int = 3
    circuit_breaker_auto_reset_s: float = 300.0


class Settings(BaseSettings):
    """Root settings object that aggregates all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="crypto-arbitrage")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],
    )

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)

    binance: BinanceSettings = Field(default_factory=BinanceSettings)
    okx: OkxSettings = Field(default_factory=OkxSettings)
    bybit: BybitSettings = Field(default_factory=BybitSettings)

    trading: TradingSettings = Field(default_factory=TradingSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    alert: AlertSettings = Field(default_factory=AlertSettings)
    live: LiveTradingSettings = Field(default_factory=LiveTradingSettings)


# Module-level singleton — import this everywhere.
settings = Settings()
