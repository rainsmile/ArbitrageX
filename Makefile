.PHONY: help dev up down build test migrate seed logs clean

# Default
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---- Development ----

dev: ## Start local development (backend + frontend + Redis)
	@bash deploy/dev.sh

dev-backend: ## Start backend only (requires Redis running)
	cd backend && ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Start frontend only
	cd frontend && npm run dev

dev-redis: ## Start Redis container for development
	docker run -d --name arbitrage-dev-redis -p 6379:6379 redis:7-alpine 2>/dev/null || docker start arbitrage-dev-redis

# ---- Docker Compose ----

up: ## Start all services with Docker Compose
	docker compose up -d --build

up-nginx: ## Start all services including Nginx reverse proxy
	docker compose --profile with-nginx up -d --build

down: ## Stop all services
	docker compose down

down-clean: ## Stop all services and remove volumes
	docker compose down -v

restart: ## Restart all services
	docker compose restart

logs: ## Tail all service logs
	docker compose logs -f

logs-backend: ## Tail backend logs only
	docker compose logs -f backend

logs-frontend: ## Tail frontend logs only
	docker compose logs -f frontend

ps: ## Show running services
	docker compose ps

# ---- Database ----

migrate: ## Run Alembic migrations
	cd backend && ../.venv/bin/alembic upgrade head

migrate-docker: ## Run migrations inside Docker
	docker compose exec backend alembic upgrade head

seed: ## Seed database with initial data
	cd backend && ../.venv/bin/python -m app.db.seed

seed-docker: ## Seed database inside Docker
	docker compose exec backend python -m app.db.seed

db-reset: ## Reset database (drop all + migrate + seed)
	cd backend && ../.venv/bin/alembic downgrade base && ../.venv/bin/alembic upgrade head
	$(MAKE) seed

# ---- Testing ----

test: ## Run all backend tests
	cd backend && ../.venv/bin/python -m pytest tests/ -v

test-fast: ## Run tests without verbose output
	cd backend && ../.venv/bin/python -m pytest tests/ -q

test-cov: ## Run tests with coverage report
	cd backend && ../.venv/bin/python -m pytest tests/ -v --cov=app --cov-report=term-missing

test-docker: ## Run tests inside Docker
	docker compose exec backend python -m pytest tests/ -v

# ---- Build ----

build: ## Build Docker images
	docker compose build

build-backend: ## Build backend Docker image
	docker build -t arbitrage-backend ./backend

build-frontend: ## Build frontend Docker image
	docker build -t arbitrage-frontend ./frontend

# ---- Linting ----

lint: ## Run backend linter (ruff)
	cd backend && ../.venv/bin/ruff check app/ tests/

lint-fix: ## Auto-fix lint issues
	cd backend && ../.venv/bin/ruff check --fix app/ tests/

typecheck: ## Run mypy type checking
	cd backend && ../.venv/bin/mypy app/

# ---- Setup ----

setup: ## Initial project setup (create venv, install deps)
	python3.12 -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install
	@echo "\n✅ Setup complete. Copy .env.example to .env and customize."

# ---- Cleanup ----

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf backend/.ruff_cache frontend/.next frontend/out
	@echo "✅ Cleaned"
