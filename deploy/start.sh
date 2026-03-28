#!/usr/bin/env bash
# ArbitrageX Production Deployment
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=== ArbitrageX Production Deployment ===${NC}"

# 1. Check prerequisites
command -v docker >/dev/null 2>&1 || { echo -e "${RED}❌ Docker not found${NC}"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo -e "${RED}❌ docker compose not found${NC}"; exit 1; }

# 2. Check .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}No .env found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}⚠️  Please edit .env with your configuration before continuing.${NC}"
fi

# 3. Build and start
echo "Building and starting services..."
docker compose up -d --build

# 4. Wait for services
echo "Waiting for services to be healthy..."

for i in $(seq 1 30); do
    if docker compose exec -T backend curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend healthy${NC}"
        break
    fi
    echo "  Waiting for backend... ($i/30)"
    sleep 2
done

# 5. Run migrations
echo "Running database migrations..."
docker compose exec -T backend alembic upgrade head 2>/dev/null && echo -e "${GREEN}✅ Migrations complete${NC}" || echo -e "${YELLOW}⚠️  Migration skipped (may already be current)${NC}"

# 6. Seed data (optional)
echo "Seeding initial data..."
docker compose exec -T backend python -m app.db.seed 2>/dev/null && echo -e "${GREEN}✅ Seed data inserted${NC}" || echo -e "${YELLOW}⚠️  Seed skipped${NC}"

# 7. Show status
echo ""
echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}  ArbitrageX Deployment Complete${NC}"
echo -e "${CYAN}================================================${NC}"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo -e "  Frontend:  ${GREEN}http://localhost:${FRONTEND_PORT:-3000}${NC}"
echo -e "  Backend:   ${GREEN}http://localhost:${API_PORT:-8000}${NC}"
echo -e "  API Docs:  ${GREEN}http://localhost:${API_PORT:-8000}/docs${NC}"
echo -e "${CYAN}================================================${NC}"
