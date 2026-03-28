"""Initial schema -- all tables.

Revision ID: 001
Revises: None
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ exchanges
    op.create_table(
        "exchanges",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False, comment="Internal exchange identifier (e.g. binance, okx)"),
        sa.Column("display_name", sa.String(100), nullable=False, comment="Human-readable exchange name"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, comment="Whether this exchange is enabled for trading"),
        sa.Column("api_status", sa.String(20), nullable=False, default="UNKNOWN", comment="REST API connectivity status"),
        sa.Column("ws_status", sa.String(20), nullable=False, default="UNKNOWN", comment="WebSocket connectivity status"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True, comment="Last successful heartbeat timestamp"),
        sa.Column("config_json", sa.JSON(), nullable=True, comment="Exchange-specific configuration (rate limits, endpoints, etc.)"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exchanges_name", "exchanges", ["name"])
    op.create_index("ix_exchanges_is_active", "exchanges", ["is_active"])

    # ------------------------------------------------------------------ exchange_symbols
    op.create_table(
        "exchange_symbols",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("exchange_id", sa.CHAR(36), sa.ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(30), nullable=False, comment="Unified symbol (e.g. BTC/USDT)"),
        sa.Column("base_asset", sa.String(20), nullable=False, comment="Base asset (e.g. BTC)"),
        sa.Column("quote_asset", sa.String(20), nullable=False, comment="Quote asset (e.g. USDT)"),
        sa.Column("price_precision", sa.Integer(), nullable=False, default=8, comment="Decimal places for price"),
        sa.Column("quantity_precision", sa.Integer(), nullable=False, default=8, comment="Decimal places for quantity"),
        sa.Column("min_quantity", sa.Numeric(28, 12), nullable=True, comment="Minimum order quantity"),
        sa.Column("max_quantity", sa.Numeric(28, 12), nullable=True, comment="Maximum order quantity"),
        sa.Column("min_notional", sa.Numeric(28, 12), nullable=True, comment="Minimum notional value (price * quantity)"),
        sa.Column("tick_size", sa.Numeric(28, 12), nullable=True, comment="Minimum price movement"),
        sa.Column("step_size", sa.Numeric(28, 12), nullable=True, comment="Minimum quantity movement"),
        sa.Column("maker_fee", sa.Numeric(10, 6), nullable=True, comment="Maker fee rate (e.g. 0.001 = 0.1%)"),
        sa.Column("taker_fee", sa.Numeric(10, 6), nullable=True, comment="Taker fee rate"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, comment="Whether this pair is enabled"),
        sa.Column("status", sa.String(20), nullable=False, default="TRADING", comment="Exchange-reported status"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exchange_symbols_exchange_symbol", "exchange_symbols", ["exchange_id", "symbol"], unique=True)
    op.create_index("ix_exchange_symbols_symbol", "exchange_symbols", ["symbol"])
    op.create_index("ix_exchange_symbols_base_quote", "exchange_symbols", ["base_asset", "quote_asset"])
    op.create_index("ix_exchange_symbols_is_active", "exchange_symbols", ["is_active"])

    # ------------------------------------------------------------------ balances
    op.create_table(
        "balances",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("exchange_id", sa.CHAR(36), sa.ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset", sa.String(20), nullable=False, comment="Asset symbol (e.g. BTC, USDT)"),
        sa.Column("free", sa.Numeric(28, 12), nullable=False, default=0, comment="Available balance"),
        sa.Column("locked", sa.Numeric(28, 12), nullable=False, default=0, comment="Balance locked in open orders"),
        sa.Column("total", sa.Numeric(28, 12), nullable=False, default=0, comment="Total balance (free + locked)"),
        sa.Column("usd_value", sa.Numeric(28, 8), nullable=True, comment="Estimated USD value"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="Last balance refresh time"),
    )
    op.create_index("ix_balances_exchange_asset", "balances", ["exchange_id", "asset"], unique=True)
    op.create_index("ix_balances_asset", "balances", ["asset"])

    # ------------------------------------------------------------------ market_ticks
    op.create_table(
        "market_ticks",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("exchange_id", sa.CHAR(36), nullable=False, comment="Exchange UUID (denormalized for speed)"),
        sa.Column("symbol", sa.String(30), nullable=False, comment="Unified symbol (e.g. BTC/USDT)"),
        sa.Column("bid", sa.Numeric(28, 12), nullable=False, comment="Best bid price"),
        sa.Column("ask", sa.Numeric(28, 12), nullable=False, comment="Best ask price"),
        sa.Column("bid_size", sa.Numeric(28, 12), nullable=True, comment="Best bid quantity"),
        sa.Column("ask_size", sa.Numeric(28, 12), nullable=True, comment="Best ask quantity"),
        sa.Column("last_price", sa.Numeric(28, 12), nullable=True, comment="Last traded price"),
        sa.Column("volume_24h", sa.Numeric(28, 8), nullable=True, comment="24-hour trading volume"),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="Exchange-reported or local capture timestamp"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_market_ticks_exchange_symbol", "market_ticks", ["exchange_id", "symbol"])
    op.create_index("ix_market_ticks_symbol_ts", "market_ticks", ["symbol", "timestamp"])
    op.create_index("ix_market_ticks_timestamp", "market_ticks", ["timestamp"])

    # ------------------------------------------------------------------ orderbook_snapshots
    op.create_table(
        "orderbook_snapshots",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("exchange_id", sa.CHAR(36), nullable=False, comment="Exchange UUID (denormalized for speed)"),
        sa.Column("symbol", sa.String(30), nullable=False, comment="Unified symbol"),
        sa.Column("bids_json", sa.JSON(), nullable=True, comment="Array of [price, qty] bid levels"),
        sa.Column("asks_json", sa.JSON(), nullable=True, comment="Array of [price, qty] ask levels"),
        sa.Column("depth_levels", sa.Integer(), nullable=True, comment="Number of depth levels captured"),
        sa.Column("spread", sa.Numeric(28, 12), nullable=True, comment="Best ask - best bid"),
        sa.Column("mid_price", sa.Numeric(28, 12), nullable=True, comment="(Best bid + best ask) / 2"),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="Snapshot capture timestamp"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_orderbook_snapshots_exchange_symbol", "orderbook_snapshots", ["exchange_id", "symbol"])
    op.create_index("ix_orderbook_snapshots_symbol_ts", "orderbook_snapshots", ["symbol", "timestamp"])
    op.create_index("ix_orderbook_snapshots_timestamp", "orderbook_snapshots", ["timestamp"])

    # ------------------------------------------------------------------ arbitrage_opportunities
    op.create_table(
        "arbitrage_opportunities",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("strategy_type", sa.Enum("CROSS_EXCHANGE", "TRIANGULAR", "FUTURES_SPOT", name="strategy_type_enum", create_constraint=True), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=True, comment="JSON array of symbols involved"),
        sa.Column("exchanges", sa.JSON(), nullable=True, comment="JSON array of exchange names involved"),
        sa.Column("buy_exchange", sa.String(50), nullable=True, comment="Exchange to buy from"),
        sa.Column("sell_exchange", sa.String(50), nullable=True, comment="Exchange to sell on"),
        sa.Column("buy_price", sa.Numeric(28, 12), nullable=True, comment="Best ask on buy exchange"),
        sa.Column("sell_price", sa.Numeric(28, 12), nullable=True, comment="Best bid on sell exchange"),
        sa.Column("spread_pct", sa.Numeric(12, 6), nullable=True, comment="Raw spread percentage"),
        sa.Column("theoretical_profit_pct", sa.Numeric(12, 6), nullable=True, comment="Profit % before fees and slippage"),
        sa.Column("estimated_net_profit_pct", sa.Numeric(12, 6), nullable=True, comment="Estimated profit % after fees and slippage"),
        sa.Column("estimated_slippage_pct", sa.Numeric(12, 6), nullable=True, comment="Estimated slippage based on orderbook depth"),
        sa.Column("executable_quantity", sa.Numeric(28, 12), nullable=True, comment="Max executable quantity in base asset"),
        sa.Column("executable_value_usdt", sa.Numeric(28, 8), nullable=True, comment="Executable notional value in USDT"),
        sa.Column("buy_fee_pct", sa.Numeric(10, 6), nullable=True, comment="Taker fee on buy side"),
        sa.Column("sell_fee_pct", sa.Numeric(10, 6), nullable=True, comment="Taker fee on sell side"),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=True, comment="0-1 confidence score"),
        sa.Column("risk_flags", sa.JSON(), nullable=True, comment="JSON map of risk flag names to details"),
        sa.Column("orderbook_depth_buy", sa.Numeric(28, 8), nullable=True, comment="Orderbook depth on buy side (USDT)"),
        sa.Column("orderbook_depth_sell", sa.Numeric(28, 8), nullable=True, comment="Orderbook depth on sell side (USDT)"),
        sa.Column("is_executable", sa.Boolean(), nullable=False, default=False, comment="Whether opportunity passes all pre-trade checks"),
        sa.Column("rejection_reason", sa.Text(), nullable=True, comment="Reason the opportunity was rejected"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="Timestamp when opportunity was first detected"),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True, comment="Timestamp when opportunity expired"),
        sa.Column("status", sa.Enum("DETECTED", "EXECUTING", "EXECUTED", "EXPIRED", "REJECTED", name="opportunity_status_enum", create_constraint=True), nullable=False, default="DETECTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_opportunities_status", "arbitrage_opportunities", ["status"])
    op.create_index("ix_opportunities_strategy", "arbitrage_opportunities", ["strategy_type"])
    op.create_index("ix_opportunities_detected_at", "arbitrage_opportunities", ["detected_at"])
    op.create_index("ix_opportunities_is_executable", "arbitrage_opportunities", ["is_executable"])
    op.create_index("ix_opportunities_buy_sell_exchange", "arbitrage_opportunities", ["buy_exchange", "sell_exchange"])

    # ------------------------------------------------------------------ execution_plans
    op.create_table(
        "execution_plans",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("opportunity_id", sa.CHAR(36), sa.ForeignKey("arbitrage_opportunities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("strategy_type", sa.Enum("CROSS_EXCHANGE", "TRIANGULAR", "FUTURES_SPOT", name="strategy_type_enum", create_constraint=False), nullable=False),
        sa.Column("mode", sa.Enum("PAPER", "LIVE", name="execution_mode_enum", create_constraint=True), nullable=False, comment="PAPER or LIVE trading mode"),
        sa.Column("target_quantity", sa.Numeric(28, 12), nullable=True, comment="Planned quantity in base asset"),
        sa.Column("target_value_usdt", sa.Numeric(28, 8), nullable=True, comment="Planned notional in USDT"),
        sa.Column("planned_profit_pct", sa.Numeric(12, 6), nullable=True, comment="Expected profit %"),
        sa.Column("status", sa.Enum("PENDING", "SUBMITTING", "PARTIAL_FILLED", "FILLED", "HEDGING", "COMPLETED", "FAILED", "ABORTED", name="execution_plan_status_enum", create_constraint=True), nullable=False, default="PENDING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_profit_pct", sa.Numeric(12, 6), nullable=True, comment="Realized profit %"),
        sa.Column("actual_profit_usdt", sa.Numeric(28, 8), nullable=True, comment="Realized profit in USDT"),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True, comment="Total execution wall-clock time in ms"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True, comment="Arbitrary execution metadata"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_execution_plans_status", "execution_plans", ["status"])
    op.create_index("ix_execution_plans_opportunity", "execution_plans", ["opportunity_id"])
    op.create_index("ix_execution_plans_mode", "execution_plans", ["mode"])
    op.create_index("ix_execution_plans_started_at", "execution_plans", ["started_at"])

    # ------------------------------------------------------------------ execution_legs
    op.create_table(
        "execution_legs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("execution_plan_id", sa.CHAR(36), sa.ForeignKey("execution_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("leg_index", sa.Integer(), nullable=False, comment="Order of this leg within the plan (0-based)"),
        sa.Column("exchange", sa.String(50), nullable=False, comment="Exchange name for this leg"),
        sa.Column("symbol", sa.String(30), nullable=False, comment="Trading pair for this leg"),
        sa.Column("side", sa.Enum("BUY", "SELL", name="leg_side_enum", create_constraint=True), nullable=False),
        sa.Column("planned_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("planned_quantity", sa.Numeric(28, 12), nullable=True),
        sa.Column("actual_price", sa.Numeric(28, 12), nullable=True),
        sa.Column("actual_quantity", sa.Numeric(28, 12), nullable=True),
        sa.Column("fee", sa.Numeric(28, 12), nullable=True, comment="Fee amount"),
        sa.Column("fee_asset", sa.String(20), nullable=True, comment="Asset in which fee was charged"),
        sa.Column("slippage_pct", sa.Numeric(12, 6), nullable=True, comment="Actual slippage vs planned price"),
        sa.Column("order_id", sa.CHAR(36), nullable=True, comment="Internal Order UUID"),
        sa.Column("exchange_order_id", sa.String(100), nullable=True, comment="Exchange-assigned order ID"),
        sa.Column("status", sa.Enum("PENDING", "SUBMITTED", "PARTIAL_FILLED", "FILLED", "CANCELED", "FAILED", name="leg_status_enum", create_constraint=True), nullable=False, default="PENDING"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_execution_legs_plan", "execution_legs", ["execution_plan_id"])
    op.create_index("ix_execution_legs_status", "execution_legs", ["status"])
    op.create_index("ix_execution_legs_exchange_symbol", "execution_legs", ["exchange", "symbol"])

    # ------------------------------------------------------------------ orders
    op.create_table(
        "orders",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("execution_leg_id", sa.CHAR(36), sa.ForeignKey("execution_legs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("exchange", sa.String(50), nullable=False, comment="Exchange name"),
        sa.Column("symbol", sa.String(30), nullable=False, comment="Unified symbol"),
        sa.Column("side", sa.Enum("BUY", "SELL", name="order_side_enum", create_constraint=True), nullable=False),
        sa.Column("order_type", sa.Enum("LIMIT", "MARKET", name="order_type_enum", create_constraint=True), nullable=False),
        sa.Column("price", sa.Numeric(28, 12), nullable=True, comment="Limit price (null for MARKET)"),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False, comment="Requested quantity"),
        sa.Column("filled_quantity", sa.Numeric(28, 12), nullable=True, default=0, comment="Cumulative filled quantity"),
        sa.Column("avg_fill_price", sa.Numeric(28, 12), nullable=True, comment="Volume-weighted avg fill price"),
        sa.Column("fee", sa.Numeric(28, 12), nullable=True, comment="Total fee charged"),
        sa.Column("fee_asset", sa.String(20), nullable=True, comment="Fee denomination asset"),
        sa.Column("status", sa.Enum("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", name="order_status_enum", create_constraint=True), nullable=False, default="NEW"),
        sa.Column("exchange_order_id", sa.String(100), nullable=True, comment="Exchange-assigned order ID"),
        sa.Column("client_order_id", sa.String(100), nullable=True, comment="Client-generated order ID"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_response_json", sa.JSON(), nullable=True, comment="Raw exchange API response"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_orders_exchange_symbol", "orders", ["exchange", "symbol"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_exchange_order_id", "orders", ["exchange_order_id"])
    op.create_index("ix_orders_client_order_id", "orders", ["client_order_id"])
    op.create_index("ix_orders_submitted_at", "orders", ["submitted_at"])
    op.create_index("ix_orders_execution_leg", "orders", ["execution_leg_id"])

    # ------------------------------------------------------------------ risk_events
    op.create_table(
        "risk_events",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("rule_name", sa.String(100), nullable=False, comment="Name of the risk rule that triggered"),
        sa.Column("rule_category", sa.String(50), nullable=True, comment="Category grouping (e.g. exposure, latency, spread)"),
        sa.Column("severity", sa.Enum("INFO", "WARNING", "CRITICAL", name="risk_severity_enum", create_constraint=True), nullable=False),
        sa.Column("event_type", sa.Enum("BLOCKED", "WARNING", "ALERT", name="risk_event_type_enum", create_constraint=True), nullable=False),
        sa.Column("opportunity_id", sa.CHAR(36), sa.ForeignKey("arbitrage_opportunities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("execution_id", sa.CHAR(36), sa.ForeignKey("execution_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True, comment="Structured details of the risk event"),
        sa.Column("threshold_value", sa.Numeric(28, 12), nullable=True, comment="Configured threshold that was breached"),
        sa.Column("actual_value", sa.Numeric(28, 12), nullable=True, comment="Actual observed value"),
        sa.Column("message", sa.Text(), nullable=True, comment="Human-readable description"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_risk_events_severity", "risk_events", ["severity"])
    op.create_index("ix_risk_events_event_type", "risk_events", ["event_type"])
    op.create_index("ix_risk_events_rule_name", "risk_events", ["rule_name"])
    op.create_index("ix_risk_events_opportunity", "risk_events", ["opportunity_id"])
    op.create_index("ix_risk_events_execution", "risk_events", ["execution_id"])
    op.create_index("ix_risk_events_created_at", "risk_events", ["created_at"])

    # ------------------------------------------------------------------ alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False, comment="Alert category (e.g. PRICE_SPIKE, EXCHANGE_DOWN)"),
        sa.Column("severity", sa.Enum("INFO", "WARNING", "CRITICAL", name="alert_severity_enum", create_constraint=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, comment="Short alert headline"),
        sa.Column("message", sa.Text(), nullable=True, comment="Detailed alert body"),
        sa.Column("source", sa.String(100), nullable=True, comment="Component that generated the alert"),
        sa.Column("is_read", sa.Boolean(), nullable=False, default=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, default=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True, comment="Structured context for the alert"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_is_read", "alerts", ["is_read"])
    op.create_index("ix_alerts_is_resolved", "alerts", ["is_resolved"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    # ------------------------------------------------------------------ strategy_configs
    op.create_table(
        "strategy_configs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False, comment="Unique strategy name"),
        sa.Column("strategy_type", sa.Enum("CROSS_EXCHANGE", "TRIANGULAR", "FUTURES_SPOT", name="strategy_type_enum", create_constraint=False), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column("exchanges", sa.JSON(), nullable=True, comment="JSON array of exchange names to monitor"),
        sa.Column("symbols", sa.JSON(), nullable=True, comment="JSON array of symbols to monitor"),
        sa.Column("min_profit_threshold_pct", sa.Numeric(10, 6), nullable=True, comment="Minimum net profit % to trigger execution"),
        sa.Column("max_order_value_usdt", sa.Numeric(28, 8), nullable=True, comment="Max notional per execution"),
        sa.Column("max_concurrent_executions", sa.Integer(), nullable=True, default=1, comment="Max parallel execution plans"),
        sa.Column("min_depth_usdt", sa.Numeric(28, 8), nullable=True, comment="Min orderbook depth required (USDT)"),
        sa.Column("max_slippage_pct", sa.Numeric(10, 6), nullable=True, comment="Max tolerable slippage %"),
        sa.Column("scan_interval_ms", sa.Integer(), nullable=True, default=500, comment="Opportunity scan interval in ms"),
        sa.Column("blacklist_symbols", sa.JSON(), nullable=True, comment="Symbols to always skip"),
        sa.Column("whitelist_symbols", sa.JSON(), nullable=True, comment="If set, only trade these symbols"),
        sa.Column("custom_params", sa.JSON(), nullable=True, comment="Strategy-specific parameters"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_strategy_configs_strategy_type", "strategy_configs", ["strategy_type"])
    op.create_index("ix_strategy_configs_is_enabled", "strategy_configs", ["is_enabled"])
    op.create_index("ix_strategy_configs_name", "strategy_configs", ["name"])

    # ------------------------------------------------------------------ pnl_records
    op.create_table(
        "pnl_records",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("execution_id", sa.CHAR(36), sa.ForeignKey("execution_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("strategy_type", sa.Enum("CROSS_EXCHANGE", "TRIANGULAR", "FUTURES_SPOT", name="strategy_type_enum", create_constraint=False), nullable=False),
        sa.Column("exchange_buy", sa.String(50), nullable=True, comment="Buy-side exchange"),
        sa.Column("exchange_sell", sa.String(50), nullable=True, comment="Sell-side exchange"),
        sa.Column("symbol", sa.String(30), nullable=False, comment="Traded symbol"),
        sa.Column("gross_profit_usdt", sa.Numeric(28, 8), nullable=True, comment="Gross profit before fees"),
        sa.Column("fees_usdt", sa.Numeric(28, 8), nullable=True, comment="Total fees in USDT"),
        sa.Column("net_profit_usdt", sa.Numeric(28, 8), nullable=True, comment="Net profit after fees"),
        sa.Column("slippage_usdt", sa.Numeric(28, 8), nullable=True, comment="Slippage cost in USDT"),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True, comment="End-to-end execution time"),
        sa.Column("mode", sa.Enum("PAPER", "LIVE", name="execution_mode_enum", create_constraint=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pnl_records_execution", "pnl_records", ["execution_id"])
    op.create_index("ix_pnl_records_strategy", "pnl_records", ["strategy_type"])
    op.create_index("ix_pnl_records_symbol", "pnl_records", ["symbol"])
    op.create_index("ix_pnl_records_mode", "pnl_records", ["mode"])
    op.create_index("ix_pnl_records_created_at", "pnl_records", ["created_at"])

    # ------------------------------------------------------------------ rebalance_suggestions
    op.create_table(
        "rebalance_suggestions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("asset", sa.String(20), nullable=False, comment="Asset to rebalance"),
        sa.Column("from_exchange", sa.String(50), nullable=False, comment="Source exchange"),
        sa.Column("to_exchange", sa.String(50), nullable=False, comment="Destination exchange"),
        sa.Column("suggested_quantity", sa.Numeric(28, 12), nullable=True, comment="Recommended transfer quantity"),
        sa.Column("reason", sa.Text(), nullable=True, comment="Why rebalance is suggested"),
        sa.Column("status", sa.Enum("PENDING", "APPROVED", "EXECUTED", "DISMISSED", name="rebalance_status_enum", create_constraint=True), nullable=False, default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rebalance_suggestions_asset", "rebalance_suggestions", ["asset"])
    op.create_index("ix_rebalance_suggestions_status", "rebalance_suggestions", ["status"])
    op.create_index("ix_rebalance_suggestions_created_at", "rebalance_suggestions", ["created_at"])

    # ------------------------------------------------------------------ system_events
    op.create_table(
        "system_events",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("event_type", sa.String(50), nullable=False, comment="Event category (e.g. STARTUP, SHUTDOWN, ERROR)"),
        sa.Column("source", sa.String(100), nullable=True, comment="Component that emitted the event"),
        sa.Column("message", sa.Text(), nullable=True, comment="Human-readable description"),
        sa.Column("details_json", sa.JSON(), nullable=True, comment="Structured event data"),
        sa.Column("severity", sa.Enum("INFO", "WARNING", "CRITICAL", name="system_severity_enum", create_constraint=True), nullable=False, default="INFO"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_events_event_type", "system_events", ["event_type"])
    op.create_index("ix_system_events_severity", "system_events", ["severity"])
    op.create_index("ix_system_events_source", "system_events", ["source"])
    op.create_index("ix_system_events_created_at", "system_events", ["created_at"])

    # ------------------------------------------------------------------ audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("action", sa.String(50), nullable=False, comment="Action performed (e.g. CREATE, UPDATE, DELETE)"),
        sa.Column("actor", sa.String(100), nullable=True, comment="User or service that performed the action"),
        sa.Column("resource_type", sa.String(50), nullable=True, comment="Type of resource affected"),
        sa.Column("resource_id", sa.String(100), nullable=True, comment="ID of the resource affected"),
        sa.Column("details_json", sa.JSON(), nullable=True, comment="Before/after snapshot or relevant context"),
        sa.Column("ip_address", sa.String(45), nullable=True, comment="Client IP address (supports IPv6)"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("system_events")
    op.drop_table("rebalance_suggestions")
    op.drop_table("pnl_records")
    op.drop_table("orders")
    op.drop_table("execution_legs")
    op.drop_table("execution_plans")
    op.drop_table("risk_events")
    op.drop_table("alerts")
    op.drop_table("strategy_configs")
    op.drop_table("arbitrage_opportunities")
    op.drop_table("orderbook_snapshots")
    op.drop_table("market_ticks")
    op.drop_table("balances")
    op.drop_table("exchange_symbols")
    op.drop_table("exchanges")

    # Drop enum types created by MySQL (only needed for PostgreSQL, but safe to include)
    for enum_name in [
        "strategy_type_enum",
        "opportunity_status_enum",
        "execution_mode_enum",
        "execution_plan_status_enum",
        "leg_side_enum",
        "leg_status_enum",
        "order_side_enum",
        "order_type_enum",
        "order_status_enum",
        "risk_severity_enum",
        "risk_event_type_enum",
        "alert_severity_enum",
        "rebalance_status_enum",
        "system_severity_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
