"""Версия приложения.

Номер версии (SemVer: МАЖОРНАЯ.МИНОРНАЯ.ПАТЧ) хранится в одном месте — файле VERSION в корне
репозитория. Коммит и время сборки подставляет деплой (аргументы сборки Docker → переменные
окружения CUREME_COMMIT и CUREME_BUILT_AT), поэтому по /api/version видно, какая именно сборка
сейчас работает на сервере.
"""

import os
import re
from functools import lru_cache
from pathlib import Path

# В репозитории это <корень>/VERSION, в Docker-образе — /app/VERSION.
VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read_version(path: Path = VERSION_FILE) -> str:
    version = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    return version if SEMVER.match(version) else "0.0.0"


@lru_cache
def app_version() -> dict:
    return {
        "version": read_version(),
        "commit": os.environ.get("CUREME_COMMIT") or None,
        "built_at": os.environ.get("CUREME_BUILT_AT") or None,
    }
