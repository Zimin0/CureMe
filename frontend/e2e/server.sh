#!/usr/bin/env bash
# Поднимает настоящий бэкенд для e2e-тестов: чистая база, миграции, собранный фронтенд.
# Фронтенд нужно собрать заранее: npm run build.
set -euo pipefail
cd "$(dirname "$0")/../../backend"
PY="${PYTHON:-python3}"
export CUREME_DATABASE_URL="sqlite:///$(mktemp -d)/e2e.db"
export CUREME_MEDIA_DIR="$(mktemp -d)"
export CUREME_FRONTEND_DIST="$(cd ../frontend && pwd)/dist"
export CUREME_REMOTE_LOOKUP=false
export CUREME_RATE_LIMIT=false  # тесты заводят десятки аккаунтов с одного адреса
export CUREME_ADMIN_EMAILS='["e2e-admin@example.com"]'
export CUREME_SECRET_KEY=e2e-secret-e2e-secret-e2e-secret-e2e-secret
"$PY" -m alembic upgrade head
exec "$PY" -m uvicorn app.main:app --port "${E2E_PORT:-8765}"
