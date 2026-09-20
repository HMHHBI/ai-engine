#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

cleanup() {
  echo "=== [4/4] Restoring Backend container to Dev DB (hassan_ai_db) ==="
  cd "$PROJECT_ROOT"
  docker compose -f docker-compose.yml -f docker-compose.override.yml up -d backend
}
trap cleanup EXIT

echo "=== [1/4] Switching Backend container to Test DB (hassan_ai_test) ==="
docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.test.yml up -d backend

echo "=== [2/4] Ensuring Migrations & Test Seed in hassan_ai_test ==="
docker exec -e DATABASE_URL=postgresql://postgres:postgres@db:5432/hassan_ai_test chat_backend alembic upgrade head > /dev/null 2>&1
docker exec -e DATABASE_URL=postgresql://postgres:postgres@db:5432/hassan_ai_test chat_backend python scripts/seed_m3_test_data.py

echo "=== [3/4] Running Playwright M3 Regression Suite ==="
cd "$PROJECT_ROOT/frontend"
npx playwright test e2e/m3_smoke.spec.ts e2e/m3_auth_journeys.spec.ts e2e/m3_chat_journeys.spec.ts e2e/m3_document_rag.spec.ts --project=desktop
