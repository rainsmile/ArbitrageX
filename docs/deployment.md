# Deployment Guide

## Docker Compose Deployment

The simplest production-like deployment uses Docker Compose.

### 1. Prepare environment

Create a `.env` file in the project root:

```bash
# Database
DATABASE_URL=mysql+aiomysql://myuser:STRONG_PASSWORD@host.docker.internal:3306/mydb?charset=utf8mb4

# Redis (uses the compose-internal service)
REDIS_URL=redis://redis:6379/0

# Trading
TRADING_PAPER_MODE=false
TRADING_ENABLED_EXCHANGES=["binance","okx","bybit"]

# Exchange credentials
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret
```

### 2. Build and start

```bash
docker compose up -d --build
```

Services:
- **redis** -- port 6379, data persisted to `redis_data` volume
- **backend** -- port 8000, health check at `/health`
- **frontend** -- port 3000, depends on backend health

### 3. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:3000
```

## Environment Configuration

### Required variables

| Variable                      | Description                          | Default              |
|-------------------------------|--------------------------------------|----------------------|
| `DATABASE_URL`                | Async MySQL connection string        | local dev string     |
| `REDIS_URL`                   | Redis connection string              | `redis://localhost:6379/0` |
| `TRADING_PAPER_MODE`          | `true` for paper, `false` for live   | `true`               |
| `TRADING_ENABLED_EXCHANGES`   | JSON list of exchange names          | all three            |

### Exchange credentials

| Variable              | Required for live trading on that exchange |
|-----------------------|-------------------------------------------|
| `BINANCE_API_KEY`     | Binance                                   |
| `BINANCE_API_SECRET`  | Binance                                   |
| `OKX_API_KEY`         | OKX                                       |
| `OKX_API_SECRET`      | OKX                                       |
| `OKX_PASSPHRASE`      | OKX                                       |
| `BYBIT_API_KEY`       | Bybit                                     |
| `BYBIT_API_SECRET`    | Bybit                                     |

### Risk tuning

| Variable                       | Description                        | Default   |
|--------------------------------|------------------------------------|-----------|
| `RISK_MAX_ORDER_VALUE_USDT`    | Max single order value             | 10000     |
| `RISK_MAX_POSITION_VALUE_USDT` | Max total open position value      | 50000     |
| `RISK_MAX_DAILY_LOSS_USDT`     | Stop trading after this daily loss | 500       |
| `RISK_MAX_CONSECUTIVE_FAILURES`| Pause after N failures             | 5         |
| `RISK_MAX_SLIPPAGE_PCT`        | Max tolerated slippage percent     | 0.15      |
| `RISK_MIN_PROFIT_THRESHOLD_PCT`| Min spread to consider             | 0.05      |

## Database Setup

### MySQL installation

```bash
# Docker approach
docker run -d --name arbitrage-mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=mydb \
  -e MYSQL_USER=myuser \
  -e MYSQL_PASSWORD=STRONG_PASSWORD \
  -p 3306:3306 \
  mysql:8.0

# Or use an existing MySQL instance and create the database manually.
```

### Run migrations

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

### Seed initial data

Some routes (e.g., `/api/strategies/seed`) can populate default strategy configs.
Call after first deployment:

```bash
curl -X POST http://localhost:8000/api/strategies/seed
```

## Nginx Reverse Proxy

A ready-to-use Nginx config is at `deploy/nginx/default.conf`. It proxies:

- `/api/*` and `/health` to the backend (port 8000)
- `/ws/*` to the backend with WebSocket upgrade headers
- `/docs`, `/redoc`, `/openapi.json` to the backend
- Everything else to the frontend (port 3000)

### Adding to Docker Compose

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./deploy/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    - ./certs:/etc/nginx/certs:ro  # for HTTPS
  depends_on:
    - backend
    - frontend
  networks:
    - arbitrage
```

### HTTPS with Let's Encrypt

Use certbot or a Docker image like `certbot/certbot` to obtain certificates.
Update `default.conf` to listen on 443 and reference the cert/key paths.
Redirect port 80 to 443.

## Production Checklist

- [ ] Set strong, unique passwords for MySQL and all exchange API keys
- [ ] Set `TRADING_PAPER_MODE=false` only after thorough paper-trading validation
- [ ] Configure `allowed_origins` in settings to restrict CORS to your domain
- [ ] Enable HTTPS via Nginx with valid TLS certificates
- [ ] Set up log rotation (Docker handles this with `--log-opt max-size`)
- [ ] Configure external monitoring (see Monitoring section)
- [ ] Set Docker resource limits (memory, CPU) for each service
- [ ] Backup the MySQL database on a regular schedule
- [ ] Use Docker secrets or a vault for credentials instead of `.env` files
- [ ] Test disaster recovery: restore from backup, verify system restarts cleanly
- [ ] Review and tune risk parameters for your capital and risk tolerance
- [ ] Verify WebSocket connections remain stable over 24+ hours

## Scaling Considerations

- **Backend**: Run multiple uvicorn workers behind a load balancer. Note that the
  in-memory EventBus and MarketDataService cache are per-process, so a single process
  is currently recommended. For multi-process scaling, move the event bus and cache to
  Redis Pub/Sub.
- **Frontend**: Deploy as a static export behind a CDN, or run multiple Next.js
  instances behind a load balancer.
- **Database**: Add read replicas for analytics queries. Keep the primary for writes.
- **Redis**: Use Redis Sentinel or Cluster mode for high availability.
- **Orchestration**: For larger deployments, consider Kubernetes with Helm charts.

## Monitoring Recommendations

- **Metrics**: Expose Prometheus metrics from the backend (or scrape the `/api/system/metrics`
  endpoint). Visualize with Grafana.
- **Error tracking**: Integrate Sentry for Python exceptions and frontend JS errors.
- **Log aggregation**: Ship Docker logs to an ELK stack (Elasticsearch, Logstash, Kibana)
  or Grafana Loki.
- **Uptime**: Use an external monitor (e.g., UptimeRobot) to hit `/health` regularly.
- **Alerting**: Configure Grafana alerts or PagerDuty for critical thresholds
  (e.g., daily loss exceeded, exchange disconnected, backend unhealthy).
