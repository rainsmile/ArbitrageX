# Development Guide

## Prerequisites

- **Python 3.12+** -- backend runtime
- **Node.js 20+** and npm -- frontend (Next.js)
- **Docker** and Docker Compose -- for Redis and MySQL (or run them natively)
- **MySQL 8.0+** -- primary database
- **Redis 7+** -- caching and rate-limiting state
- **Git** -- version control

## First-Time Setup

### 1. Clone and enter the repository

```bash
git clone <repo-url>
cd arbitrage
```

### 2. Start infrastructure services

```bash
docker compose up -d redis
# MySQL can run via Docker or a local install. Ensure a database exists:
# CREATE DATABASE mydb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
# CREATE USER 'myuser'@'%' IDENTIFIED BY 'YourPassword123!';
# GRANT ALL PRIVILEGES ON mydb.* TO 'myuser'@'%';
```

### 3. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment

Copy the example and edit as needed:

```bash
cp .env.example .env   # if an example exists, otherwise create .env
```

Key variables (defaults work for local dev):

```
DATABASE_URL=mysql+aiomysql://myuser:YourPassword123!@127.0.0.1:3306/mydb?charset=utf8mb4
REDIS_URL=redis://localhost:6379/0
TRADING_PAPER_MODE=true
TRADING_ENABLED_EXCHANGES=["binance","okx","bybit"]
```

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Frontend setup

```bash
cd ../frontend
npm install
```

## Local Development

### Start the backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is available at `http://localhost:8000`. Interactive docs at `/docs` (Swagger)
and `/redoc`.

### Start the frontend

```bash
cd frontend
npm run dev
```

The dashboard is available at `http://localhost:3000`.

### Quick start with Docker Compose

```bash
docker compose up --build
```

This starts Redis, backend (port 8000), and frontend (port 3000).

## Project Structure

```
arbitrage/
  backend/
    alembic/            # Database migration scripts
    app/
      api/routes/       # FastAPI route modules (one per domain)
      core/             # Config, events, exceptions, logging, dependencies
      db/               # Session factory, Redis client
      exchanges/        # Exchange adapter implementations
      models/           # SQLAlchemy ORM models (16 tables)
      schemas/          # Pydantic request/response schemas
      services/         # Business logic services
      simulation/       # (placeholder for simulation module)
      strategies/       # (placeholder for strategy module)
      utils/            # Shared utilities
    tests/              # pytest test suite
  frontend/
    src/                # Next.js app (TypeScript, Tailwind CSS)
    public/             # Static assets
  deploy/
    nginx/              # Nginx reverse proxy config
    dev.sh              # Dev startup helper script
    start.sh            # Production startup script
  docs/                 # Documentation (this directory)
  docker-compose.yml    # Service orchestration
```

## Adding a New Exchange Adapter

1. Create `backend/app/exchanges/<exchange_name>.py`.
2. Subclass `BaseExchangeAdapter` from `backend/app/exchanges/base.py`.
3. Implement all abstract methods: `initialize()`, `shutdown()`, `get_ticker()`,
   `get_orderbook()`, `place_order()`, `cancel_order()`, `get_balances()`, etc.
4. Register the adapter in `ExchangeFactory` (`backend/app/exchanges/factory.py`) --
   add a branch in `create_from_settings()` that instantiates your adapter when the
   exchange name appears in `settings.trading.enabled_exchanges`.
5. Add credential settings in `backend/app/core/config.py` (subclass `ExchangeKeySettings`
   with an appropriate `env_prefix`).

## Adding a New Risk Rule

1. Create a class inheriting from `RiskRule` in `backend/app/services/risk_engine.py`
   (or a separate file imported there).
2. Implement the `async check(self, opportunity, context) -> RiskCheckResult` method.
3. Instantiate the rule in `RiskEngine._build_default_rules()` so it is included in the
   evaluation pipeline.
4. Add any new config fields to `RiskSettings` in `backend/app/core/config.py` if needed.

## Adding a New API Route

1. Create `backend/app/api/routes/<domain>.py`.
2. Define a FastAPI `APIRouter` with a `prefix` (e.g., `/api/my-feature`).
3. Implement endpoint functions using `@router.get()`, `@router.post()`, etc.
4. Register the module in the `router_modules` list inside `_mount_routers()` in
   `backend/app/main.py`.

## Debugging Tips

- **Backend logs**: Loguru writes to stdout by default. In Docker, use
  `docker compose logs -f backend`.
- **Frontend**: Use React DevTools and the browser Network tab to inspect API calls
  and WebSocket frames.
- **Redis state**: `redis-cli monitor` shows commands in real time.
  `redis-cli keys "risk:*"` to inspect risk counters.
- **Database**: Use any MySQL client or a tool like Adminer.
  `alembic history` shows migration state.
- **WebSocket testing**: Use `websocat ws://localhost:8000/ws/opportunities` to
  subscribe to a channel from the command line.
- **Swagger UI**: Visit `http://localhost:8000/docs` to interactively test endpoints.

## Code Style

- **Backend**: `ruff` for linting and formatting, `mypy` for type checking.
  Run `ruff check .` and `mypy app/` from the `backend/` directory.
- **Frontend**: ESLint with TypeScript strict mode. Run `npm run lint`.
- **Commit messages**: Conventional commits recommended
  (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, etc.).
- **Branch naming**: `feature/<name>`, `fix/<name>`, `chore/<name>`.
