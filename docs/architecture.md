# Architecture Overview

This document describes the high-level architecture of the Crypto Arbitrage system,
covering all major components, data flows, state machines, and infrastructure.

## System Components

### Exchange Adapters

Located in `backend/app/exchanges/`. Each adapter subclasses `BaseExchangeAdapter` and
normalizes exchange-specific wire formats into standardized dataclasses (`StandardTicker`,
`StandardOrderbook`, `OrderResult`, etc.).

| Adapter  | File         | Purpose                                     |
|----------|--------------|---------------------------------------------|
| Binance  | `binance.py` | Production adapter using ccxt + WebSocket    |
| OKX      | `okx.py`     | Production adapter using ccxt + WebSocket    |
| Bybit    | `bybit.py`   | Production adapter using ccxt + WebSocket    |
| Mock     | `mock.py`    | Paper-trading adapter with simulated fills   |

`ExchangeFactory` (`factory.py`) reads `settings.trading.enabled_exchanges` and
instantiates the appropriate adapters. In paper mode, a `MockExchangeAdapter` wraps
real market data but simulates order execution.

### MarketDataService

`backend/app/services/market_data.py`

- Subscribes to WebSocket ticker and orderbook streams from each exchange adapter.
- Falls back to REST polling when a WebSocket connection drops.
- Maintains an in-memory cache of the latest tickers and orderbooks.
- Optionally writes snapshots to Redis for cross-process access.
- Publishes `MARKET_UPDATE` and `BALANCE_UPDATED` events on the EventBus.

### ArbitrageScanner

`backend/app/services/scanner.py`

Runs a background loop that reads cached market data and identifies two types of
opportunities:

- **Cross-exchange spread**: Same symbol on two exchanges with a profitable bid-ask
  spread after fees.
- **Triangular path**: Three trading pairs on a single exchange forming a cycle
  (e.g., BTC/USDT -> ETH/BTC -> ETH/USDT) whose combined rate exceeds 1.0 after fees.

Detected opportunities are published as `OPPORTUNITY_FOUND` events and persisted to
the `arbitrage_opportunities` table.

### ExecutionCoordinator

`backend/app/services/execution_coordinator.py`

Orchestrates the full lifecycle of an arbitrage execution:

1. Receives an opportunity (from scanner or manual trigger).
2. Delegates to `ExecutionPlanner` to build a plan.
3. Runs pre-trade risk checks via `RiskEngine`.
4. Hands the plan to `ExecutionEngine` for order placement.
5. Monitors execution progress, handles partial fills and hedging.
6. Updates `InventoryManager`, `AnalyticsService`, and `AuditService` on completion.

### ExecutionEngine

`backend/app/services/execution_engine.py`

Handles the low-level order placement and status polling:

- Places orders through exchange adapters.
- Monitors fill status with configurable timeout.
- Supports both paper (simulated) and live execution modes.
- Publishes `EXECUTION_STARTED`, `EXECUTION_COMPLETED`, and `EXECUTION_FAILED` events.

### ExecutionPlanner

`backend/app/services/execution_planner.py`

Builds an `ExecutionPlan` (with individual legs) from a raw opportunity:

- Determines order sides, quantities, and price limits.
- Considers available balances from `InventoryManager`.
- Optionally runs a simulation via `SimulationService` before committing.

### RiskEngine

`backend/app/services/risk_engine.py`

Evaluates opportunities against a configurable pipeline of 12 pre-trade rules:

| # | Rule                          | What it checks                                    |
|---|-------------------------------|---------------------------------------------------|
| 1 | `MaxOrderValueRule`           | Single order value <= limit                       |
| 2 | `MaxDailyLossRule`            | Cumulative daily loss <= limit (via Redis)        |
| 3 | `MaxConsecutiveFailuresRule`  | Consecutive failures < threshold (via Redis)      |
| 4 | `MaxSlippageRule`             | Estimated slippage <= tolerance                   |
| 5 | `MinProfitRule`               | Spread meets minimum pct and USDT thresholds      |
| 6 | `MinDepthRule`                | Orderbook depth sufficient for planned quantity   |
| 7 | `DataFreshnessRule`           | Market data age within acceptable window          |
| 8 | `BalanceSufficiencyRule`      | Enough balance on relevant exchanges              |
| 9 | `MaxExposureRule`             | Per-exchange exposure <= limit                    |
|10 | `MaxConcurrentRule`           | Active executions < concurrency cap               |
|11 | `SymbolWhitelistBlacklistRule`| Symbol allowed by whitelist/blacklist config      |
|12 | `MinOrderbookDepthRule`       | Orderbook depth passes absolute threshold         |

Additionally:

- **In-trade**: Timeout monitoring during order execution.
- **Post-trade**: Profit deviation check after completion (actual vs. expected).

### InventoryManager

`backend/app/services/inventory.py`

- Tracks balances per exchange per asset.
- Syncs with live exchange balances on startup and periodically.
- Calculates allocation and exposure summaries.
- Generates rebalance suggestions when holdings drift.
- Updates on `EXECUTION_COMPLETED` and `BALANCE_UPDATED` events.

### AlertService

`backend/app/services/alert_service.py`

6 built-in alert rules that fire on event bus triggers:

1. Exchange disconnected
2. Market data stale
3. Consecutive execution failures
4. Daily loss limit exceeded
5. Low balance on an exchange
6. High exposure concentration

Notification channels: structured log output, Telegram (via HTTP), and email (planned).
Alerts are persisted to the `alerts` table and published as `ALERT_TRIGGERED` events.

### AnalyticsService

`backend/app/services/analytics.py`

- Aggregates PnL per execution, per period, per exchange, per symbol, per strategy.
- Failure analysis: categorizes failure reasons, calculates rates.
- Slippage analysis: compares estimated vs. actual execution prices.
- Dashboard endpoint combining key KPIs into a single payload.

### AuditService

`backend/app/services/audit.py`

- Subscribes to all EventBus event types.
- Writes structured JSON entries to a ring buffer (in-memory) and to the `audit_logs` table.
- Provides query endpoints filtered by execution ID, time range, and event type.
- Returns aggregate stats (events per type, per hour).

### StateMachine

Execution and leg lifecycle states are defined as enums in `backend/app/models/execution.py`
and enforced by the `ExecutionCoordinator`.

---

## Data Flow

```
1.  Exchange WS/REST  -->  ExchangeAdapter
2.  ExchangeAdapter   -->  MarketDataService  (in-memory ticker/orderbook cache)
3.  MarketDataService  -->  ArbitrageScanner  (reads cache each scan cycle)
4.  ArbitrageScanner   -->  OpportunityCandidate  (cross-exchange or triangular)
5.  Opportunity        -->  ExecutionCoordinator.execute_opportunity()
6.  Coordinator        -->  ExecutionPlanner.build_plan()
7.  Coordinator        -->  RiskEngine.evaluate()   (12 pre-trade rules)
8.  Coordinator        -->  ExecutionEngine.execute()
9.  ExecutionEngine    -->  ExchangeAdapter.place_order()
10. Result             -->  InventoryManager.on_execution_completed()
11. Result             -->  AnalyticsService  (PnL record)
12. All steps          -->  AuditService  (audit trail)
13. Events             -->  EventBus  -->  WebSocket bridge  -->  Frontend
```

---

## Execution State Machine

### Plan-level states

```
PENDING --> SUBMITTING --> PARTIAL_FILLED --> FILLED --> COMPLETED
                |                  |                       |
                v                  v                       v
              FAILED            HEDGING               ABORTED
                                  |
                                  v
                              COMPLETED / FAILED
```

### Leg-level states

```
PENDING --> SUBMITTED --> PARTIAL_FILLED --> FILLED
                |                |
                v                v
             FAILED          CANCELED
```

The `ExecutionCoordinator` transitions plan state based on the aggregate status of all
legs. If any leg fails, the coordinator may enter `HEDGING` to unwind already-filled legs.

---

## Risk Engine Pipeline

```
Opportunity arrives
    |
    v
[Pre-trade]  12 rules evaluated in sequence
    |         Any violation --> REJECTED (+ RISK_VIOLATION event)
    v
[Approved]   Execution proceeds
    |
    v
[In-trade]   Timeout monitoring per leg
    |         Timeout --> cancel + hedge attempt
    v
[Post-trade] Profit deviation check
             Large deviation --> alert + risk event logged
```

---

## Database Schema

16 tables managed by SQLAlchemy models with Alembic migrations:

| Table                      | Model file          | Purpose                              |
|----------------------------|---------------------|--------------------------------------|
| `exchanges`                | `exchange.py`       | Registered exchange metadata         |
| `exchange_symbols`         | `symbol.py`         | Tradable symbols per exchange        |
| `balances`                 | `balance.py`        | Per-exchange, per-asset balances     |
| `market_ticks`             | `market.py`         | Historical ticker snapshots          |
| `orderbook_snapshots`      | `market.py`         | Historical orderbook snapshots       |
| `arbitrage_opportunities`  | `opportunity.py`    | Detected opportunities               |
| `execution_plans`          | `execution.py`      | Execution plan records               |
| `execution_legs`           | `execution.py`      | Individual legs within a plan        |
| `orders`                   | `order.py`          | Order records placed on exchanges    |
| `strategy_configs`         | `strategy.py`       | Strategy configuration (enable/disable, params) |
| `risk_events`              | `risk.py`           | Logged risk violations               |
| `pnl_records`              | `analytics.py`      | Per-execution PnL records            |
| `alerts`                   | `alert.py`          | Alert history                        |
| `rebalance_suggestions`    | `analytics.py`      | Generated rebalance recommendations  |
| `system_events`            | `system.py`         | System lifecycle events              |
| `audit_logs`               | `system.py`         | Structured audit trail               |

All models use a UUID primary key and `created_at`/`updated_at` timestamps via `TimestampMixin`.

---

## Event Bus

The `EventBus` (`backend/app/core/events.py`) is an in-process async pub/sub system.

### Event Types

| EventType              | Published by                     |
|------------------------|----------------------------------|
| `MARKET_UPDATE`        | MarketDataService                |
| `OPPORTUNITY_FOUND`    | ArbitrageScanner                 |
| `OPPORTUNITY_EXPIRED`  | ArbitrageScanner                 |
| `EXECUTION_STARTED`    | ExecutionEngine                  |
| `EXECUTION_COMPLETED`  | ExecutionEngine / Coordinator    |
| `EXECUTION_FAILED`     | ExecutionEngine / Coordinator    |
| `RISK_VIOLATION`       | RiskEngine                       |
| `ALERT_TRIGGERED`      | AlertService                     |
| `BALANCE_UPDATED`      | InventoryManager                 |
| `SYSTEM_EVENT`         | Application lifespan             |

Each event is wrapped in an immutable `Event` dataclass with a UUID `id`, `timestamp`,
`type`, and `data` dict.

---

## WebSocket Channels

The backend exposes 4 WebSocket endpoints that bridge EventBus events to the frontend:

| Endpoint             | Channel          | Events forwarded                                      |
|----------------------|------------------|-------------------------------------------------------|
| `/ws/market`         | `market`         | `MARKET_UPDATE`, `BALANCE_UPDATED`                    |
| `/ws/opportunities`  | `opportunities`  | `OPPORTUNITY_FOUND`, `OPPORTUNITY_EXPIRED`            |
| `/ws/executions`     | `executions`     | `EXECUTION_STARTED`, `EXECUTION_COMPLETED`, `EXECUTION_FAILED` |
| `/ws/alerts`         | `alerts`         | `RISK_VIOLATION`, `ALERT_TRIGGERED`, `SYSTEM_EVENT`   |

Clients connect via standard WebSocket and receive JSON messages in the format:

```json
{
  "type": "opportunity_found",
  "data": { ... },
  "id": "hex-uuid",
  "timestamp": 1711612800.0
}
```

Clients may send `ping` or `{"type":"ping"}` to receive a `pong` keep-alive response.
