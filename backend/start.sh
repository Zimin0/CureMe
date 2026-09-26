#!/bin/sh
# Старт контейнера: миграции базы, при необходимости перенос из SQLite, затем сервер.
set -e

SQLITE_FILE="${CUREME_SQLITE_IMPORT:-/data/cureme.db}"
case "$CUREME_DATABASE_URL" in
  postgresql*)
    if [ -f "$SQLITE_FILE" ]; then
      # Старую базу сначала догоняем до последней версии схемы, чтобы таблицы совпали с Postgres.
      CUREME_DATABASE_URL="sqlite:///$SQLITE_FILE" alembic upgrade head
      alembic upgrade head
      python -m app.sqlite_import "$SQLITE_FILE"
    else
      alembic upgrade head
    fi
    ;;
  *)
    alembic upgrade head
    ;;
esac

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
