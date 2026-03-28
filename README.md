# ArbitrageX - Cryptocurrency Arbitrage Platform

> Professional-grade cryptocurrency cross-exchange and triangular arbitrage detection, simulation, and execution platform.

---

**RISK WARNING**: This software involves cryptocurrency trading which carries significant financial risk. Live trading mode can result in real financial losses. Use at your own risk. Always start with paper/simulation mode.

---

## Table of Contents

- [Overview](#overview)
- [Core Capabilities](#core-capabilities)
- [Tech Stack](#tech-stack)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Trading Modes](#trading-modes)
- [Database](#database)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Current Limitations & Future Work](#current-limitations--future-work)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Overview

ArbitrageX is a full-stack cryptocurrency arbitrage platform that monitors price discrepancies across multiple centralized exchanges in real time, identifies profitable trading opportunities, and executes trades automatically with built-in risk management.

The system supports two primary arbitrage strategies:

- **Cross-exchange arbitrage** -- Buy an asset on the exchange where it is cheapest and simultaneously sell on the exchange where it is most expensive.
- **Triangular arbitrage** -- Exploit pricing inefficiencies between three trading pairs on a single exchange (e.g., BTC/USDT -> ETH/BTC -> ETH/USDT).

**Key differentiators:**

- Real-time WebSocket market data from multiple exchanges with REST fallback
- Sub-second opportunity detection with configurable scan intervals
- 12-rule configurable risk engine with pre-trade, in-trade, and post-trade evaluation
- Full state machine execution lifecycle (10 states) with audit trail
- Paper trading and simulation modes for risk-free strategy validation
- Professional trading dashboard with live data streaming

**Current status:** Fully functional in paper/simulation mode. Live trading mode is implemented but requires valid exchange API keys with trading permissions.

---

## Core Capabilities

- **Multi-exchange market data aggregation** -- Binance, OKX, Bybit, Upbit, Bithumb, and a Mock adapter for testing
- **Cross-exchange arbitrage detection and execution** -- Automatic spread calculation across all exchange pairs
- **Single-exchange triangular arbitrage** -- Three-leg cycle detection with fee-adjusted profit estimation
- **12-rule configurable risk engine** -- Max order value, daily loss limit, consecutive failure protection, slippage threshold, balance sufficiency, exposure limits, data freshness, orderbook depth, symbol whitelist/blacklist, and more
- **State machine execution lifecycle** -- 10 states from opportunity detection through completion or failure, with full transition audit
- **Real-time WebSocket streaming** -- Market data, opportunities, executions, and alerts pushed to the frontend in real time
- **Professional trading dashboard** -- Next.js application with 10 pages covering market data, opportunities, executions, analytics, inventory, risk, alerts, and settings
- **Paper trading and simulation** -- Full execution pipeline without real orders; simulates fills, slippage, and partial execution
- **Inventory management and rebalancing** -- Tracks balances across all exchanges with allocation analysis and rebalance suggestions
- **Multi-channel alert system** -- Telegram bot, email (SMTP), and in-app notifications for risk violations, execution failures, and system events
- **Analytics and PnL tracking** -- Profit/loss breakdowns by exchange, symbol, strategy, and time period with theoretical vs. actual comparison
- **Audit trail** -- Complete execution history with state transitions, timestamps, and metadata
- **Docker deployment** -- Single-command deployment with Docker Compose including Redis, backend, frontend, and optional Nginx reverse proxy

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.x (async), Pydantic v2, Pydantic Settings |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS, Radix UI, shadcn/ui |
| Charts | Recharts |
| Database | MySQL 8.0 (aiomysql async driver) |
| Cache / Pub-Sub | Redis 7 (hiredis) |
| State Management | Zustand, TanStack React Query v5 |
| Exchange SDKs | ccxt, httpx, websockets |
| Logging | Loguru (structured JSON) |
| Migrations | Alembic |
| Serialization | orjson |
| Containerization | Docker, Docker Compose |
| Reverse Proxy | Nginx (optional) |

---

## Architecture Overview

ArbitrageX is composed of loosely coupled service modules that communicate through an internal async event bus. Data flows through the system as follows:

1. **Exchange Adapters** connect to exchanges via WebSocket and REST. Each adapter (Binance, OKX, Bybit, Mock) normalizes exchange-specific wire formats into standardized dataclasses.
2. **MarketDataService** aggregates real-time ticker and orderbook data from all connected exchanges. Publishes `MARKET_UPDATE` events and caches data in Redis.
3. **ArbitrageScanner** continuously scans for cross-exchange and triangular opportunities. Evaluates spread, depth, fees, and estimated net profit before emitting `OPPORTUNITY_FOUND` events.
4. **ExecutionPlanner** creates execution plans from opportunities, determining leg order, exchange selection, and order parameters.
5. **ExecutionCoordinator** orchestrates the full lifecycle: plan -> risk check -> execute -> hedge -> record. Manages the state machine through 10 states.
6. **RiskEngine** evaluates every opportunity against 12 configurable rules before execution is approved. Monitors in-trade and validates post-trade. Publishes `RISK_VIOLATION` events when rules are breached.
7. **InventoryManager** tracks balances across all exchanges, computes allocation percentages, and generates rebalance suggestions.
8. **AlertService** dispatches notifications through configured channels (application log, Telegram, email) when risk violations, execution failures, or system events occur.
9. **AuditService** records all state transitions, decisions, and system events for compliance and debugging.
10. **Frontend** receives real-time updates via four WebSocket channels (`/ws/market`, `/ws/opportunities`, `/ws/executions`, `/ws/alerts`) and displays them on the trading dashboard.

---

## Project Structure

```
arbitrage/
├── backend/                         # Python FastAPI backend
│   ├── app/
│   │   ├── main.py                  # Application entry point, WebSocket endpoints, lifespan
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings (all env vars)
│   │   │   ├── events.py            # Async event bus
│   │   │   ├── state_machine.py     # Generic finite state machine with audit logging
│   │   │   ├── calculations.py      # Spread, profit, fee calculations
│   │   │   ├── dependencies.py      # FastAPI dependency injection
│   │   │   ├── exceptions.py        # Custom error hierarchy
│   │   │   └── logging.py           # Loguru setup
│   │   ├── api/routes/              # 13 API route modules (70+ endpoints)
│   │   │   ├── system.py            # /api/system/* (health, metrics, exchanges)
│   │   │   ├── market.py            # /api/market/* (tickers, orderbooks, spreads)
│   │   │   ├── scanner_status.py    # /api/scanner/* (status, opportunities, trigger)
│   │   │   ├── executions.py        # /api/executions/* (list, detail, execute)
│   │   │   ├── orders.py            # /api/orders/* (list, detail)
│   │   │   ├── risk.py              # /api/risk/* (rules, events, exposure)
│   │   │   ├── inventory.py         # /api/inventory/* (balances, allocation)
│   │   │   ├── analytics.py         # /api/analytics/* (PnL, profit, failures)
│   │   │   ├── alerts.py            # /api/alerts/* (list, acknowledge, resolve)
│   │   │   ├── audit.py             # /api/audit/* (entries, execution trail)
│   │   │   ├── simulate.py          # /api/simulate/* (cross-exchange, triangular)
│   │   │   ├── strategies.py        # /api/strategies/* (list, update, enable)
│   │   │   └── exchanges.py         # /api/exchanges/* (status, configuration)
│   │   ├── services/                # Business logic (9 service modules)
│   │   │   ├── market_data.py       # Real-time market data aggregation
│   │   │   ├── scanner.py           # Arbitrage opportunity scanner
│   │   │   ├── execution_engine.py  # Trade execution state machine
│   │   │   ├── execution_planner.py # Execution plan builder
│   │   │   ├── execution_coordinator.py # Orchestrates plan -> execute -> record
│   │   │   ├── risk_engine.py       # 12-rule risk evaluation engine
│   │   │   ├── simulation.py        # Paper trading / simulation engine
│   │   │   ├── inventory.py         # Balance and allocation management
│   │   │   ├── analytics.py         # PnL computation and analysis
│   │   │   ├── alert_service.py     # Multi-channel alert dispatch
│   │   │   └── audit.py             # Audit trail service
│   │   ├── exchanges/               # Exchange adapters
│   │   │   ├── base.py              # Abstract adapter + standardized dataclasses
│   │   │   ├── binance.py           # Binance adapter (WebSocket + REST)
│   │   │   ├── okx.py              # OKX adapter
│   │   │   ├── bybit.py            # Bybit adapter
│   │   │   ├── mock.py             # Mock adapter for testing
│   │   │   └── factory.py          # Adapter factory
│   │   ├── models/                  # SQLAlchemy ORM (13 model files, 15+ tables)
│   │   │   ├── base.py             # Declarative base
│   │   │   ├── exchange.py         # exchanges table
│   │   │   ├── symbol.py           # exchange_symbols table
│   │   │   ├── balance.py          # balances table
│   │   │   ├── market.py           # market_snapshots table
│   │   │   ├── opportunity.py      # arbitrage_opportunities table
│   │   │   ├── execution.py        # execution_plans, execution_legs tables
│   │   │   ├── order.py            # orders table
│   │   │   ├── risk.py             # risk_events table
│   │   │   ├── strategy.py         # strategy_configs table
│   │   │   ├── analytics.py        # pnl_records, rebalance_suggestions tables
│   │   │   ├── alert.py            # alerts table
│   │   │   └── system.py           # system_events table
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── db/
│   │   │   ├── session.py          # Async SQLAlchemy session factory
│   │   │   ├── redis.py            # Redis client wrapper
│   │   │   └── seed.py             # Database seed data
│   │   └── utils/
│   │       └── helpers.py
│   ├── tests/                       # 285 pytest tests (14 test files)
│   │   ├── conftest.py
│   │   ├── test_calculations.py
│   │   ├── test_state_machine.py
│   │   ├── test_mock_exchange.py
│   │   ├── test_scanner.py
│   │   ├── test_risk_engine.py
│   │   ├── test_simulation.py
│   │   ├── test_market_data.py
│   │   ├── test_execution_coordinator.py
│   │   ├── test_execution_planner.py
│   │   ├── test_inventory.py
│   │   ├── test_alert_service.py
│   │   ├── test_audit.py
│   │   └── test_utils.py
│   ├── alembic/                     # Database migrations
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── requirements.txt
│   ├── alembic.ini
│   └── Dockerfile
├── frontend/                        # Next.js React frontend
│   ├── src/
│   │   ├── app/                     # 10 pages (App Router)
│   │   │   ├── page.tsx             # Dashboard home
│   │   │   ├── layout.tsx           # Root layout
│   │   │   ├── providers.tsx        # Query + WebSocket providers
│   │   │   ├── market/              # Market data and tickers
│   │   │   ├── opportunities/       # Arbitrage opportunities
│   │   │   ├── executions/          # Execution plans and history
│   │   │   ├── analytics/           # PnL and analytics
│   │   │   ├── inventory/           # Balance and allocation
│   │   │   ├── risk/                # Risk rules and events
│   │   │   ├── alerts/              # System alerts
│   │   │   └── settings/            # System settings
│   │   ├── components/              # 33 UI components
│   │   │   ├── charts/              # Recharts chart components
│   │   │   ├── layout/              # Shell, sidebar, navigation
│   │   │   └── ui/                  # Reusable UI primitives (shadcn/ui)
│   │   ├── hooks/                   # Custom React hooks
│   │   │   ├── useApi.ts            # React Query API hooks
│   │   │   └── useWebSocket.ts      # WebSocket connection hook
│   │   ├── lib/                     # Utilities
│   │   │   ├── api.ts               # HTTP API client
│   │   │   ├── ws.ts                # WebSocket client
│   │   │   ├── utils.ts             # General utilities
│   │   │   └── mock-data.ts         # Mock data for development
│   │   ├── store/                   # Zustand state stores
│   │   │   └── index.ts
│   │   └── types/                   # TypeScript type definitions
│   │       └── index.ts
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── Dockerfile
├── deploy/                          # Deployment configs
│   ├── nginx/                       # Nginx reverse proxy configuration
│   ├── dev.sh                       # Local development startup script
│   └── start.sh                     # Production deployment script
├── docs/                            # Documentation
├── docker-compose.yml               # Production Docker Compose
├── .env.example                     # Environment variable template
└── README.md
```

---

## Quick Start

### Prerequisites

- Docker and Docker Compose (for containerized deployment)
- Python 3.12+ (for local backend development)
- Node.js 20+ and npm (for local frontend development)
- MySQL 8.0 server (running on host or remotely)
- Redis 7 (included in Docker Compose)

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone and configure
git clone <repo-url> && cd arbitrage
cp .env.example .env
# Edit .env with your MySQL credentials and desired configuration

# 2. Start all services (Redis, backend, frontend)
docker compose up -d --build

# 3. Check status
docker compose ps

# 4. View backend logs
docker compose logs -f backend

# 5. Run database migrations
docker compose exec backend alembic upgrade head

# 6. Seed initial data (exchanges, strategies)
docker compose exec backend python -c \
  "import asyncio; from app.db.seed import seed_all; asyncio.run(seed_all())"
```

**Access the application:**

| Service | URL |
|---|---|
| Frontend Dashboard | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Documentation (Swagger) | http://localhost:8000/docs |
| API Documentation (ReDoc) | http://localhost:8000/redoc |

### Option 2: Local Development

```bash
# 1. Clone and configure
git clone <repo-url> && cd arbitrage
cp .env.example .env

# 2. Start Redis (via Docker)
docker run -d --name arbitrage-redis -p 6379:6379 redis:7-alpine

# 3. Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -c "import asyncio; from app.db.seed import seed_all; asyncio.run(seed_all())"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Frontend setup (in a new terminal)
cd frontend
npm install
npm run dev

# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

---

## Environment Variables

All configuration is managed through a `.env` file in the project root. Copy `.env.example` to `.env` and adjust values as needed.

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `mysql+aiomysql://myuser:YourPassword123!@host.docker.internal:3306/mydb` | Async SQLAlchemy database URL |
| `DB_POOL_SIZE` | `10` | Connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections |

### Redis

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |

### Exchange API Keys

| Variable | Description |
|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | Binance API credentials |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_PASSPHRASE` | OKX API credentials |
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | Bybit API credentials |
| `UPBIT_API_KEY` / `UPBIT_API_SECRET` | Upbit API credentials |
| `BITHUMB_API_KEY` / `BITHUMB_API_SECRET` | Bithumb API credentials |

### Trading Configuration

| Variable | Default | Description |
|---|---|---|
| `TRADING_MODE` | `paper` | Trading mode: `paper` or `live` |
| `TRADING_PAIRS` | `BTC/USDT,ETH/USDT,XRP/USDT,SOL/USDT` | Comma-separated trading pairs to monitor |
| `ACTIVE_EXCHANGES` | `binance,upbit,bithumb` | Comma-separated list of active exchanges |

### Risk Management

| Variable | Default | Description |
|---|---|---|
| `MAX_POSITION_SIZE` | `1000.0` | Max single trade position size (USDT) |
| `MIN_PROFIT_THRESHOLD` | `0.3` | Min profit threshold percentage to execute |
| `MAX_SLIPPAGE` | `0.1` | Max allowed slippage percentage |
| `DAILY_LOSS_LIMIT` | `500.0` | Daily loss limit in USDT (stops trading if exceeded) |
| `MAX_CONCURRENT_POSITIONS` | `5` | Max concurrent open positions |

### Strategy Settings

| Variable | Default | Description |
|---|---|---|
| `PRICE_FETCH_INTERVAL` | `1.0` | Price fetch interval in seconds |
| `ORDER_BOOK_DEPTH` | `10` | Orderbook depth levels to analyze |
| `OPPORTUNITY_EXPIRY` | `5.0` | Opportunity staleness timeout in seconds |
| `ENABLE_KIMCHI_PREMIUM` | `true` | Enable Kimchi premium (KR exchange) strategy |

### Alerts and Notifications

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `""` | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | `""` | Telegram chat ID for notifications |
| `SMTP_HOST` | `""` | SMTP host for email alerts |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | `""` | SMTP username |
| `SMTP_PASSWORD` | `""` | SMTP password |
| `ALERT_EMAIL_TO` | `""` | Recipient email address |

### Logging

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | `logs/arbitrage.log` | Log file path |
| `LOG_ROTATION` | `50 MB` | Log file rotation size |
| `LOG_RETENTION` | `30 days` | Log file retention period |

### Frontend

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL (used by frontend) |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL (used for CORS) |

### Security

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | `change-me-to-a-random-string` | JWT signing secret (change in production) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRY_MINUTES` | `60` | JWT token expiry in minutes |

---

## Trading Modes

### Paper Mode (Default)

- Full execution pipeline is exercised end-to-end
- Orders are simulated -- never sent to real exchanges
- Risk checks, state machine transitions, and PnL recording are all active
- Safe for testing strategies and validating system behavior
- Set `TRADING_MODE=paper` (default)

### Mock Mode

- Uses the `MockExchangeAdapter` with simulated prices and balances
- No real API keys required
- Ideal for UI development, demos, and testing the full pipeline offline
- Enabled when no API keys are configured or when mock exchange is explicitly selected

### Live Mode

- **REAL orders on REAL exchanges with REAL money**
- Requires valid API keys with trading permissions for each enabled exchange
- Set `TRADING_MODE=live` in your `.env` file
- **Start with small position sizes. Monitor closely. Use at your own risk.**
- Ensure risk parameters are conservatively configured before enabling

---

## Database

ArbitrageX uses MySQL 8.0 with async access via aiomysql and SQLAlchemy 2.x. The schema includes 15+ tables covering exchanges, symbols, balances, market snapshots, opportunities, execution plans, orders, risk events, strategies, PnL records, alerts, and system events.

### Migrations

```bash
# Apply all migrations (local)
cd backend
alembic upgrade head

# Apply migrations (Docker)
docker compose exec backend alembic upgrade head

# Create a new migration after model changes
cd backend
alembic revision --autogenerate -m "description of changes"

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Seed Data

Seed data populates exchange configurations, default strategy configurations, and initial settings.

```bash
# Local
cd backend
python -c "import asyncio; from app.db.seed import seed_all; asyncio.run(seed_all())"

# Docker
docker compose exec backend python -c \
  "import asyncio; from app.db.seed import seed_all; asyncio.run(seed_all())"
```

### Database Tables

| Table | Description |
|---|---|
| `exchanges` | Registered exchanges with connectivity status and configuration |
| `exchange_symbols` | Trading pairs per exchange with precision and limit details |
| `balances` | Asset balances per exchange (free, locked, total, USD value) |
| `market_snapshots` | Historical market data snapshots |
| `arbitrage_opportunities` | Detected opportunities with spread, profit estimates, and status |
| `execution_plans` | Trade execution plans with state machine status tracking |
| `execution_legs` | Individual order legs within an execution plan |
| `orders` | All submitted orders with fill details and slippage |
| `risk_events` | Risk rule violations and warnings |
| `strategy_configs` | Strategy configurations (type, pairs, thresholds, enabled state) |
| `pnl_records` | Per-trade PnL records for analytics |
| `rebalance_suggestions` | System-generated rebalance recommendations |
| `alerts` | Alert records with severity, read, and resolved status |
| `system_events` | System lifecycle events |

---

## Testing

The backend test suite contains 285 tests across 14 test files covering unit tests, service tests, and integration tests.

```bash
# Run all tests
cd backend
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_scanner.py

# Run a specific test
pytest tests/test_risk_engine.py::test_function_name

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run in Docker
docker compose exec backend pytest
```

### Test Categories

**Unit tests:**
- `test_calculations.py` -- Spread, profit, and fee calculation functions
- `test_state_machine.py` -- State transition validation and audit logging
- `test_utils.py` -- Utility helper functions

**Service tests:**
- `test_scanner.py` -- Cross-exchange and triangular opportunity detection
- `test_risk_engine.py` -- All 12 risk rules and violation detection
- `test_simulation.py` -- Paper trading simulation engine
- `test_market_data.py` -- Market data aggregation and caching
- `test_mock_exchange.py` -- Mock exchange adapter (orders, cancellation, balances)
- `test_alert_service.py` -- Multi-channel alert dispatch
- `test_audit.py` -- Audit trail recording

**Integration tests:**
- `test_execution_coordinator.py` -- End-to-end execution orchestration
- `test_execution_planner.py` -- Plan construction from opportunities
- `test_inventory.py` -- Balance tracking and rebalance suggestions

---

## API Reference

ArbitrageX exposes 70+ REST endpoints organized into 13 route modules, plus 4 WebSocket channels for real-time data.

### REST Endpoints

**System** -- `/api/system/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/system/health` | Full system health (DB, Redis, exchanges) |
| `GET` | `/api/system/metrics` | Operational metrics (scan rate, success rate, avg profit) |
| `GET` | `/api/system/exchanges` | Configured exchanges with connectivity status |
| `GET` | `/api/system/ws-status` | WebSocket connection status per exchange |

**Market Data** -- `/api/market/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/market/tickers` | All tickers across exchanges |
| `GET` | `/api/market/tickers/{exchange}/{symbol}` | Specific ticker |
| `GET` | `/api/market/orderbooks/{exchange}/{symbol}` | Orderbook with configurable depth |
| `GET` | `/api/market/spreads` | Cross-exchange spread comparison |
| `GET` | `/api/market/spreads/{symbol}` | Spread detail for a symbol |
| `GET` | `/api/market/arbitrage-opportunities` | Detected opportunities (paginated, filterable) |

**Scanner** -- `/api/scanner/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/scanner/status` | Scanner running status and statistics |
| `GET` | `/api/scanner/opportunities` | Recent detected opportunities |
| `POST` | `/api/scanner/trigger` | Manually trigger a scan cycle |

**Executions** -- `/api/executions/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/executions/active` | Currently active executions |
| `GET` | `/api/executions/` | List executions (paginated, filterable) |
| `GET` | `/api/executions/{id}` | Execution detail with legs |
| `POST` | `/api/executions/` | Manually trigger execution of an opportunity |

**Orders** -- `/api/orders/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/orders/` | List orders (filterable by exchange, symbol, side, status) |
| `GET` | `/api/orders/{id}` | Get a specific order |

**Risk Management** -- `/api/risk/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/risk/rules` | List all 12 risk rules with current thresholds |
| `PUT` | `/api/risk/rules/{name}` | Update a risk rule (enable/disable, change threshold) |
| `GET` | `/api/risk/events` | List risk events (filterable by severity, rule, time range) |
| `GET` | `/api/risk/exposure` | Current risk exposure per exchange/asset |

**Inventory** -- `/api/inventory/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/inventory/balances` | All balances across exchanges |
| `GET` | `/api/inventory/balances/{exchange}` | Balances for a specific exchange |
| `GET` | `/api/inventory/allocation` | Full inventory summary with allocation breakdown |
| `GET` | `/api/inventory/rebalance-suggestions` | Rebalance suggestions |

**Analytics** -- `/api/analytics/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/analytics/summary` | PnL summary (configurable time range) |
| `GET` | `/api/analytics/profit` | Profit by time period (hour/day/week) |
| `GET` | `/api/analytics/profit/by-exchange` | Profit grouped by exchange pair |
| `GET` | `/api/analytics/profit/by-symbol` | Profit grouped by trading symbol |
| `GET` | `/api/analytics/profit/by-strategy` | Profit grouped by strategy type |
| `GET` | `/api/analytics/failures` | Failure and abort analysis |
| `GET` | `/api/analytics/slippage` | Slippage analysis |
| `GET` | `/api/analytics/dashboard` | Combined analytics dashboard |
| `GET` | `/api/analytics/opportunity-vs-execution` | Theoretical vs actual profit comparison |

**Alerts** -- `/api/alerts/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/alerts/active` | Active unresolved alerts |
| `GET` | `/api/alerts/` | List alerts (filterable by severity, read/resolved) |
| `GET` | `/api/alerts/{id}` | Get a specific alert |
| `POST` | `/api/alerts/{id}/read` | Mark alert as read |
| `POST` | `/api/alerts/{id}/resolve` | Mark alert as resolved |

**Audit** -- `/api/audit/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/audit/entries` | Audit log entries (paginated, filterable) |
| `GET` | `/api/audit/execution/{id}` | Full audit trail for an execution |
| `GET` | `/api/audit/stats` | Audit statistics |

**Simulation** -- `/api/simulate/*`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/simulate/cross-exchange` | Simulate a cross-exchange arbitrage trade |
| `POST` | `/api/simulate/triangular` | Simulate a triangular arbitrage trade |

**Strategies** -- `/api/strategies/*`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/strategies/` | List all strategy configurations |
| `GET` | `/api/strategies/{id}` | Get a specific strategy |
| `PUT` | `/api/strategies/{id}` | Update strategy configuration |
| `POST` | `/api/strategies/{id}/enable` | Enable a strategy |
| `POST` | `/api/strategies/{id}/disable` | Disable a strategy |
| `POST` | `/api/strategies/seed` | Seed default strategies |

### WebSocket Channels

| Endpoint | Description |
|---|---|
| `ws://localhost:8000/ws/market` | Real-time market data (prices, balances) |
| `ws://localhost:8000/ws/opportunities` | Arbitrage opportunity stream |
| `ws://localhost:8000/ws/executions` | Trade execution updates |
| `ws://localhost:8000/ws/alerts` | System alerts and risk violations |

**Full interactive documentation:** http://localhost:8000/docs

---

## Docker Deployment

### Standard Deployment

```bash
# Start all services (Redis, backend, frontend)
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

The Docker Compose stack includes:
- **redis** -- Redis 7 Alpine with persistence (appendonly)
- **backend** -- FastAPI application with health check
- **frontend** -- Next.js application

MySQL is expected to run externally (on the host machine or a managed service). The backend connects to it via `host.docker.internal`.

### Production Recommendations

- **Use HTTPS.** Configure Nginx with Let's Encrypt SSL certificates. Place Nginx in front of the backend and frontend services.
- **Change all default credentials.** Set strong values for `JWT_SECRET`, database passwords, and API keys in `.env`.
- **Restrict CORS origins.** Set `FRONTEND_URL` to only the specific domain(s) that should access the API.
- **Use a dedicated MySQL instance.** A managed MySQL service (e.g., AWS RDS, Cloud SQL) is recommended over a containerized database for production workloads.
- **Configure log rotation.** Ensure `LOG_ROTATION` and `LOG_RETENTION` are set to prevent disk exhaustion.
- **Set resource limits.** Add `mem_limit` and `cpus` constraints in `docker-compose.yml` for each service.
- **Use Docker secrets or a vault** for sensitive values instead of plain `.env` files.
- **Set up monitoring.** Integrate Prometheus and Grafana for metrics, alerting, and dashboards.
- **Enable health check monitoring.** Use the `/api/system/health` endpoint with an external uptime monitor.

---

## Troubleshooting / FAQ

**Frontend cannot connect to backend**
- Verify `NEXT_PUBLIC_API_URL` in `.env` points to the correct backend address.
- In Docker, the frontend container uses `http://backend:8000` (internal network). For browser requests, ensure port 8000 is exposed.

**Database connection failed**
- Verify `DATABASE_URL` has the correct host, port, username, and password.
- Ensure MySQL is running and accessible. In Docker, `host.docker.internal` maps to the host machine.
- Check that the database and user exist: `mysql -u myuser -p -e "SHOW DATABASES;"`.

**WebSocket keeps disconnecting**
- Check firewall rules -- WebSocket requires persistent TCP connections.
- If behind a reverse proxy, ensure proxy timeout and upgrade headers are configured correctly.
- Verify the backend is healthy: `curl http://localhost:8000/health`.

**No arbitrage opportunities found**
- This is normal in paper mode with mock exchanges -- the mock adapter generates limited price variation.
- Check scanner status via `GET /api/scanner/status` to confirm it is running.
- Verify `TRADING_PAIRS` and `ACTIVE_EXCHANGES` are configured correctly.
- Lower `MIN_PROFIT_THRESHOLD` for testing purposes.

**"Module not found" errors in backend**
- Ensure the virtual environment is activated: `source venv/bin/activate`.
- Run `pip install -r requirements.txt` to install all dependencies.

**Alembic migration errors**
- Ensure `DATABASE_URL` in `alembic.ini` or `.env` is correct.
- Run `alembic history` to check migration state.
- For a fresh start: `alembic downgrade base && alembic upgrade head`.

**Redis connection refused**
- Verify Redis is running: `docker ps | grep redis` or `redis-cli ping`.
- Check that `REDIS_URL` matches the actual Redis host and port.

---

## Current Limitations & Future Work

- [ ] **Authentication and authorization** -- JWT infrastructure is prepared but not yet enforced on endpoints
- [ ] **DEX integration** -- Uniswap, SushiSwap, PancakeSwap, dYdX for cross-chain arbitrage
- [ ] **Machine learning opportunity scoring** -- Predictive models for spread behavior and timing
- [ ] **Backtesting engine** -- Replay historical market data to evaluate strategy performance
- [ ] **Multi-tenant SaaS mode** -- Per-user API keys, strategy configs, and usage billing
- [ ] **Kubernetes deployment** -- Helm charts and manifests for horizontal scaling
- [ ] **Prometheus metrics endpoint** -- Native `/metrics` endpoint for monitoring integration
- [ ] **Rate limiter middleware** -- Per-client API rate limiting
- [ ] **Geographic distribution** -- Multi-region deployment for exchange latency optimization
- [ ] **Additional exchanges** -- Kraken, Coinbase, Gate.io, and other CEX adapters

---

## License

This project is licensed under the MIT License.

---

## Disclaimer

This software is provided "as-is" for educational and research purposes. Cryptocurrency trading involves substantial risk of loss and is not suitable for every investor. The developers and contributors of ArbitrageX are not responsible for any financial losses incurred through the use of this software.

- Past performance in simulation or paper trading does not guarantee future results.
- Market conditions, exchange API changes, network latency, and other factors can cause unexpected behavior.
- Always conduct your own research and risk assessment before trading with real funds.
- Start with paper trading mode and small position sizes before considering live execution.
- Comply with all applicable laws and regulations in your jurisdiction regarding cryptocurrency trading.
