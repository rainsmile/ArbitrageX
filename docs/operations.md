# Operations Guide

## Viewing Logs

### Docker logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f redis
```

### Log levels

The backend uses Loguru. The default level is `INFO`. Set the `LOG_LEVEL` environment
variable to adjust:

```
LOG_LEVEL=DEBUG    # Verbose: includes WS frames, SQL echo, rule evaluations
LOG_LEVEL=INFO     # Normal operation (default)
LOG_LEVEL=WARNING  # Only warnings and errors
```

### Structured audit logs

The `AuditService` writes structured entries to the `audit_logs` table and maintains
an in-memory ring buffer. Query via:

```bash
curl http://localhost:8000/api/audit/?limit=50
curl http://localhost:8000/api/audit/execution/{execution_id}
```

## System Health Monitoring

### Health endpoint

```bash
curl http://localhost:8000/health
```

Returns database status, Redis connectivity, WebSocket connection counts, and event bus
subscriber counts. Status is `healthy` when Redis is connected, `degraded` otherwise.

### Metrics endpoint

```bash
curl http://localhost:8000/api/system/metrics
```

Returns uptime, active execution count, opportunity counts, scanner cycle metrics,
and exchange adapter status.

### Exchange status

```bash
curl http://localhost:8000/api/system/exchanges
```

Lists each exchange adapter with its connection state and supported symbols.

### WebSocket status

```bash
curl http://localhost:8000/api/system/ws-status
```

Shows the number of connected clients per WebSocket channel.

## Common Alerts and Resolution

| Alert                        | Likely cause                         | Resolution                                    |
|------------------------------|--------------------------------------|-----------------------------------------------|
| **Exchange disconnected**    | API key invalid, rate limit hit, or network issue | Verify API keys. Check exchange status page. Restart backend if needed. |
| **Market data stale**        | WebSocket dropped, REST fallback failing | Check network connectivity. Backend auto-reconnects, but a restart may help. |
| **Consecutive failures**     | Slippage, insufficient balance, exchange errors | Review recent executions at `/api/executions/`. Fix root cause. Reset counter (see below). |
| **Daily loss exceeded**      | Strategy underperforming or market volatility | System auto-pauses trading. Review PnL at `/api/analytics/pnl-summary`. Adjust risk params or wait for next day. |
| **Low balance**              | Funds depleted on one exchange       | Deposit funds or reduce position sizes. Check `/api/inventory/balances`. |
| **High exposure**            | Concentration on one exchange        | Run rebalance: check `/api/inventory/rebalance-suggestions`. Transfer funds between exchanges. |

## Mode Switching

### Paper mode (default)

All execution goes through the `MockExchangeAdapter`, which simulates fills using real
market data. No real orders are placed.

```
TRADING_PAPER_MODE=true
```

### Live mode

Real orders are placed on configured exchanges. Switch carefully:

1. Verify exchange API keys are configured and have trading permissions.
2. Verify balances are available: `curl http://localhost:8000/api/inventory/balances`.
3. Review risk parameters: `curl http://localhost:8000/api/risk/rules`.
4. Set `TRADING_PAPER_MODE=false` in `.env`.
5. Restart the backend: `docker compose restart backend`.
6. Monitor the first few executions closely via the dashboard or WebSocket.

### Switching back to paper

Set `TRADING_PAPER_MODE=true` and restart. Any in-flight live orders will not be
automatically canceled -- check the exchange dashboards manually.

## Database Maintenance

### Backup

```bash
mysqldump -u myuser -p mydb > backup_$(date +%Y%m%d).sql
```

### Cleanup old records

Market ticks and orderbook snapshots grow quickly. Periodically delete old rows:

```sql
DELETE FROM market_ticks WHERE created_at < NOW() - INTERVAL 30 DAY;
DELETE FROM orderbook_snapshots WHERE created_at < NOW() - INTERVAL 7 DAY;
DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL 90 DAY;
DELETE FROM system_events WHERE created_at < NOW() - INTERVAL 90 DAY;
```

### Index maintenance

```sql
ANALYZE TABLE execution_plans, orders, arbitrage_opportunities, pnl_records;
```

Run periodically (weekly) to keep the query optimizer accurate.

### Migration after upgrade

```bash
cd backend && alembic upgrade head
```

## Emergency Procedures

### Stop all trading immediately

1. Set `TRADING_PAPER_MODE=true` in `.env` (or `ENABLE_LIVE_TRADING=false` if supported).
2. Restart the backend: `docker compose restart backend`.
3. Alternatively, stop the backend entirely: `docker compose stop backend`.
4. Check exchange dashboards for any open orders and cancel them manually.

### Reset risk counters

Risk state is tracked in Redis. Clear it when counters are stale or after resolving
an issue:

```bash
redis-cli DEL risk:consecutive_failures
redis-cli DEL risk:daily_loss:$(date +%Y-%m-%d)
```

### Force stop the scanner

```bash
curl -X POST http://localhost:8000/api/scanner/trigger  # if stop endpoint exists
# Otherwise restart the backend
docker compose restart backend
```

### Recover from database corruption

1. Stop the backend.
2. Restore from the latest backup: `mysql -u myuser -p mydb < backup_YYYYMMDD.sql`.
3. Run migrations: `cd backend && alembic upgrade head`.
4. Start the backend.

### Investigate a failed execution

```bash
# Get execution details
curl http://localhost:8000/api/executions/{id}/detail

# Get audit trail for that execution
curl http://localhost:8000/api/audit/execution/{id}

# Check risk events
curl http://localhost:8000/api/risk/events?limit=20
```
