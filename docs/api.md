# API Reference

## Base URL

```
http://localhost:8000
```

Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Authentication

Not yet implemented. All endpoints are currently open. JWT-based authentication is
planned for a future release.

## Response Format

Successful responses return JSON. Error responses follow a standard envelope:

```json
{
  "error": true,
  "code": 1000,
  "code_name": "UNKNOWN",
  "message": "Description of the error",
  "details": {}
}
```

HTTP status codes:
- `200` -- Success
- `400` -- Bad request / validation error
- `404` -- Resource not found
- `503` -- Service unavailable (component not initialized)
- `500` -- Internal server error

---

## Endpoints

### Health

| Method | Path      | Description              |
|--------|-----------|--------------------------|
| GET    | `/`       | Root health check        |
| GET    | `/health` | Detailed health status   |

### System

| Method | Path                      | Description                                  |
|--------|---------------------------|----------------------------------------------|
| GET    | `/api/system/health`      | System health (DB, Redis, exchanges)         |
| GET    | `/api/system/metrics`     | System metrics (uptime, counts, scanner)     |
| GET    | `/api/system/exchanges`   | List exchange adapters and their status       |
| GET    | `/api/system/ws-status`   | WebSocket connection counts per channel       |

### Market Data

| Method | Path                                          | Description                              |
|--------|-----------------------------------------------|------------------------------------------|
| GET    | `/api/market/tickers`                         | All cached tickers (optional `?exchange=`) |
| GET    | `/api/market/tickers/{exchange}/{symbol}`     | Single ticker for exchange + symbol       |
| GET    | `/api/market/orderbooks/{exchange}/{symbol}`  | Orderbook for exchange + symbol           |
| GET    | `/api/market/spreads`                         | Cross-exchange spread matrix              |
| GET    | `/api/market/freshness`                       | Data freshness per exchange per symbol    |
| GET    | `/api/market/arbitrage-opportunities`         | Recent opportunities from DB              |

### Scanner

| Method | Path                          | Description                              |
|--------|-------------------------------|------------------------------------------|
| GET    | `/api/scanner/status`         | Scanner running state and cycle metrics  |
| GET    | `/api/scanner/opportunities`  | Currently detected opportunities         |
| POST   | `/api/scanner/trigger`        | Trigger an immediate scan cycle          |

### Executions

| Method | Path                                    | Description                                    |
|--------|-----------------------------------------|------------------------------------------------|
| GET    | `/api/executions/active`                | List active (non-terminal) executions          |
| GET    | `/api/executions/`                      | List all executions (paginated, filterable)    |
| GET    | `/api/executions/{id}`                  | Get a single execution plan                    |
| POST   | `/api/executions/`                      | Create a new execution manually                |
| POST   | `/api/executions/execute-opportunity`   | Execute a detected opportunity by ID           |
| POST   | `/api/executions/cross-exchange`        | Manually trigger a cross-exchange execution    |
| POST   | `/api/executions/triangular`            | Manually trigger a triangular execution        |
| GET    | `/api/executions/active-detail`         | Active executions with full leg details        |
| GET    | `/api/executions/{id}/detail`           | Single execution with full leg details         |

#### Request body: Execute Opportunity

```json
{
  "opportunity_id": "uuid-string",
  "mode": "PAPER"
}
```

#### Request body: Cross Exchange

```json
{
  "symbol": "BTC/USDT",
  "buy_exchange": "binance",
  "sell_exchange": "okx",
  "quantity": 0.01,
  "mode": "PAPER"
}
```

#### Request body: Triangular

```json
{
  "exchange": "binance",
  "path": ["BTC/USDT", "ETH/BTC", "ETH/USDT"],
  "start_amount": 1000.0,
  "mode": "PAPER"
}
```

### Risk

| Method | Path                       | Description                              |
|--------|----------------------------|------------------------------------------|
| GET    | `/api/risk/rules`          | List all risk rules and their config     |
| PUT    | `/api/risk/rules/{name}`   | Update a risk rule (enable/disable, params) |
| GET    | `/api/risk/events`         | List recent risk violation events        |
| GET    | `/api/risk/exposure`       | Current exposure per exchange            |
| POST   | `/api/risk/check`          | Run a risk check against an opportunity  |

### Inventory

| Method | Path                                    | Description                              |
|--------|-----------------------------------------|------------------------------------------|
| GET    | `/api/inventory/balances`               | All balances across all exchanges        |
| GET    | `/api/inventory/balances/{exchange}`    | Balances for a specific exchange         |
| GET    | `/api/inventory/allocation`             | Asset allocation breakdown               |
| GET    | `/api/inventory/rebalance-suggestions`  | Suggested rebalance transfers            |
| GET    | `/api/inventory/exposure`               | Per-exchange exposure summary            |
| GET    | `/api/inventory/summary`                | Combined inventory overview              |

### Analytics

| Method | Path                                          | Description                              |
|--------|-----------------------------------------------|------------------------------------------|
| GET    | `/api/analytics/pnl-summary`                  | Aggregate PnL for a time range           |
| GET    | `/api/analytics/profit-by-period`             | PnL broken down by time period           |
| GET    | `/api/analytics/profit-by-exchange`           | PnL broken down by exchange              |
| GET    | `/api/analytics/profit-by-symbol`             | PnL broken down by trading pair          |
| GET    | `/api/analytics/profit-by-strategy`           | PnL broken down by strategy type         |
| GET    | `/api/analytics/failure-analysis`             | Failure reasons and rates                |
| GET    | `/api/analytics/slippage-analysis`            | Estimated vs. actual price comparison    |
| GET    | `/api/analytics/dashboard`                    | Combined KPI dashboard payload           |
| GET    | `/api/analytics/opportunity-vs-execution`     | Conversion funnel from opportunity to fill|

Common query parameters: `?start=ISO8601&end=ISO8601&exchange=binance&symbol=BTC/USDT`

### Alerts

| Method | Path                               | Description                              |
|--------|------------------------------------|------------------------------------------|
| GET    | `/api/alerts/active`               | List unresolved alerts                   |
| GET    | `/api/alerts/`                     | List all alerts (paginated)              |
| GET    | `/api/alerts/{id}`                 | Get a single alert                       |
| POST   | `/api/alerts/{id}/read`            | Mark an alert as read                    |
| POST   | `/api/alerts/{id}/resolve`         | Resolve an alert                         |
| POST   | `/api/alerts/{id}/acknowledge`     | Acknowledge an alert                     |

### Audit

| Method | Path                              | Description                              |
|--------|-----------------------------------|------------------------------------------|
| GET    | `/api/audit/`                     | List audit log entries (filterable)      |
| GET    | `/api/audit/execution/{id}`       | Audit trail for a specific execution     |
| GET    | `/api/audit/stats`                | Aggregate audit statistics               |

### Simulate

| Method | Path                                  | Description                              |
|--------|---------------------------------------|------------------------------------------|
| POST   | `/api/simulate/cross-exchange`        | Simulate a cross-exchange arbitrage      |
| POST   | `/api/simulate/triangular`            | Simulate a triangular arbitrage          |
| POST   | `/api/simulate/opportunity`           | Simulate execution of a detected opportunity |
| GET    | `/api/simulate/quick-scan`            | Quick scan for current opportunities     |

### Strategies

| Method | Path                                  | Description                              |
|--------|---------------------------------------|------------------------------------------|
| GET    | `/api/strategies/`                    | List all strategy configurations         |
| GET    | `/api/strategies/{id}`                | Get a single strategy config             |
| PUT    | `/api/strategies/{id}`                | Update strategy parameters               |
| POST   | `/api/strategies/{id}/enable`         | Enable a strategy                        |
| POST   | `/api/strategies/{id}/disable`        | Disable a strategy                       |
| POST   | `/api/strategies/seed`                | Seed default strategy configs            |

### Exchanges

| Method | Path                    | Description                              |
|--------|-------------------------|------------------------------------------|
| GET    | `/api/exchanges/`       | List exchange details from DB            |

### Orders

| Method | Path                    | Description                              |
|--------|-------------------------|------------------------------------------|
| GET    | `/api/orders/`          | List orders (paginated, filterable)      |

---

## WebSocket

### Connection

```
ws://localhost:8000/ws/{channel}
```

Channels: `market`, `opportunities`, `executions`, `alerts`

### Message format (server to client)

```json
{
  "type": "opportunity_found",
  "data": {
    "symbol": "BTC/USDT",
    "buy_exchange": "binance",
    "sell_exchange": "okx",
    "spread_pct": 0.12
  },
  "id": "a1b2c3d4e5f6",
  "timestamp": 1711612800.0
}
```

### Keep-alive

Send `ping` or `{"type":"ping"}` to receive:

```json
{
  "type": "pong",
  "timestamp": 1711612800.0
}
```

### Event types per channel

| Channel          | Event types                                                  |
|------------------|--------------------------------------------------------------|
| `market`         | `market_update`, `balance_updated`                           |
| `opportunities`  | `opportunity_found`, `opportunity_expired`                   |
| `executions`     | `execution_started`, `execution_completed`, `execution_failed` |
| `alerts`         | `risk_violation`, `alert_triggered`, `system_event`          |
