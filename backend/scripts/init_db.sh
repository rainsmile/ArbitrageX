#!/usr/bin/env bash
# Initialize database: wait for DB, run migrations, seed data
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$BACKEND_DIR")"

cd "$BACKEND_DIR"

echo "=== ArbitrageX Database Initialization ==="

# Step 1: Wait for database
echo "Step 1: Waiting for database..."
python scripts/wait_for_db.py
if [ $? -ne 0 ]; then
    echo "❌ Database not available. Aborting."
    exit 1
fi

# Step 2: Run Alembic migrations
echo "Step 2: Running migrations..."
alembic upgrade head
echo "✅ Migrations complete"

# Step 3: Seed initial data
echo "Step 3: Seeding data..."
python -m app.db.seed
echo "✅ Seed data inserted"

echo ""
echo "=== Database initialization complete ==="
