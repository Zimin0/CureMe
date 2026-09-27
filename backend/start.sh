#!/bin/sh
# Старт контейнера: миграции базы, при необходимости перенос из SQLite, затем сервер.
set -e

# Том /data мог быть создан старой версией от root: отдаём его пользователю app и перезапускаемся от него.
if [ "$(id -u)" = "0" ] && id app >/dev/null 2>&1; then
  mkdir -p /data
  chown -R app:app /data
  exec setpriv --reuid=app --regid=app --init-groups --no-new-privs sh "$0" "$@"
fi

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

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header
