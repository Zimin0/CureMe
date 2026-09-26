"""Одноразовый перенос данных из SQLite в PostgreSQL.

Запускается при старте контейнера (start.sh), если приложение уже смотрит в Postgres,
а в томе /data ещё лежит старая база cureme.db. Обе базы к этому моменту обновлены
миграциями до одной версии, поэтому таблицы совпадают один в один.

Перенос идёт одной транзакцией: либо переехало всё, либо ничего, и при следующем
старте попытка повторится. После успеха файл SQLite переименовывается
(cureme.db → cureme.db.imported-<время>), но не удаляется: это резервная копия.

Вручную: python -m app.sqlite_import /data/cureme.db
"""
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import Integer, String, func, insert, select, text
from sqlalchemy.engine import Engine

from . import models  # noqa: F401 — регистрирует таблицы в Base.metadata
from .config import get_settings
from .db import Base, make_engine

BATCH = 500


def _fit(table, row: dict) -> dict:
    """SQLite не следит за длиной строк, а Postgres следит. Слишком длинное аккуратно обрезаем."""
    for col in table.columns:
        value = row.get(col.name)
        if isinstance(col.type, String) and col.type.length and isinstance(value, str) and len(value) > col.type.length:
            print(f"  {table.name}.{col.name}: обрезано до {col.type.length} символов", flush=True)
            row[col.name] = value[: col.type.length]
    return row


def copy_data(source: Engine, target: Engine) -> dict[str, int]:
    """Копирует все таблицы приложения из source в target. Возвращает, сколько строк в каждой."""
    counts: dict[str, int] = {}
    with source.connect() as src, target.begin() as dst:
        # В новой базе миграции уже создали стандартные категории: заменяем их тем, что было в SQLite.
        for table in reversed(Base.metadata.sorted_tables):
            dst.execute(table.delete())
        for table in Base.metadata.sorted_tables:  # родители раньше детей: внешние ключи не ругаются
            rows = [_fit(table, dict(r._mapping)) for r in src.execute(select(table))]
            for i in range(0, len(rows), BATCH):
                dst.execute(insert(table), rows[i : i + BATCH])
            counts[table.name] = len(rows)
        if target.dialect.name == "postgresql":
            # id вставлены явно, поэтому счётчики автоинкремента надо сдвинуть за максимум
            for table in Base.metadata.sorted_tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, Integer) and pk[0].autoincrement is not False:
                    dst.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                        f"COALESCE((SELECT MAX({pk[0].name}) FROM {table.name}), 0) + 1, false)"
                    ))
    return counts


def import_sqlite(sqlite_path: Path, target_url: str) -> bool:
    """True, если данные перенесены; False, если переносить нечего или уже перенесено."""
    if not sqlite_path.is_file():
        print(f"SQLite-базы {sqlite_path} нет, переносить нечего", flush=True)
        return False
    target = make_engine(target_url)
    source = make_engine(f"sqlite:///{sqlite_path}")
    try:
        with target.connect() as conn:
            has_data = conn.execute(select(func.count()).select_from(models.User)).scalar()
        if has_data:
            print(f"В {target.url.render_as_string(hide_password=True)} уже есть пользователи, "
                  f"перенос из {sqlite_path} пропущен", flush=True)
            return False
        print(f"Переносим данные из {sqlite_path} в {target.url.render_as_string(hide_password=True)}…", flush=True)
        counts = copy_data(source, target)
    finally:
        source.dispose()
        target.dispose()
    print("Перенесено: " + ", ".join(f"{name} {n}" for name, n in counts.items()), flush=True)
    backup = sqlite_path.with_name(f"{sqlite_path.name}.imported-{datetime.now():%Y%m%d-%H%M%S}")
    sqlite_path.rename(backup)
    print(f"Старая база сохранена как {backup}", flush=True)
    return True


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/cureme.db")
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        sys.exit(f"CUREME_DATABASE_URL указывает не на Postgres ({url}), переносить некуда")
    import_sqlite(path, url)
