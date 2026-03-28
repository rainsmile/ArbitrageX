#!/usr/bin/env bash
# ArbitrageX Local Development Startup
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    docker stop arbitrage-dev-redis 2>/dev/null || true
    echo -e "${GREEN}Stopped.${NC}"
}
trap cleanup EXIT INT TERM

echo -e "${CYAN}=== ArbitrageX Development Mode ===${NC}"

# 1. Load env
if [ -f .env ]; then
    set -a; source .env; set +a
    echo -e "${GREEN}✅ .env loaded${NC}"
else
    echo -e "${YELLOW}⚠️  No .env file found. Copy .env.example to .env${NC}"
fi

# 2. Start Redis
echo "Starting Redis..."
docker run -d --name arbitrage-dev-redis -p ${REDIS_PORT:-6379}:6379 redis:7-alpine 2>/dev/null \
    || docker start arbitrage-dev-redis 2>/dev/null
echo -e "${GREEN}✅ Redis running on port ${REDIS_PORT:-6379}${NC}"

# 3. Setup Python venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3.12 -m venv .venv
    .venv/bin/pip install -q -r backend/requirements.txt
fi

# 4. Start backend
echo "Starting backend..."
cd backend
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT:-8000} --reload &
BACKEND_PID=$!
cd "$ROOT_DIR"
echo -e "${GREEN}✅ Backend starting on port ${API_PORT:-8000}${NC}"

# 5. Setup frontend if needed
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd frontend && npm install && cd "$ROOT_DIR"
fi

# 6. Start frontend
echo "Starting frontend..."
cd frontend
npm run dev -- -p ${FRONTEND_PORT:-3000} &
FRONTEND_PID=$!
cd "$ROOT_DIR"
echo -e "${GREEN}✅ Frontend starting on port ${FRONTEND_PORT:-3000}${NC}"

echo ""
echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}  ArbitrageX Development Environment Running${NC}"
echo -e "${CYAN}================================================${NC}"
echo -e "  Frontend:  ${GREEN}http://localhost:${FRONTEND_PORT:-3000}${NC}"
echo -e "  Backend:   ${GREEN}http://localhost:${API_PORT:-8000}${NC}"
echo -e "  API Docs:  ${GREEN}http://localhost:${API_PORT:-8000}/docs${NC}"
echo -e "  Redis:     ${GREEN}localhost:${REDIS_PORT:-6379}${NC}"
echo -e "${CYAN}================================================${NC}"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop all services"
echo ""

wait
