#!/usr/bin/env python3
"""Какие тесты запускать для этих изменений.

В pull request CI гоняет не всё подряд, а только разделы, которые проверяют
изменённый код. Полный прогон остаётся на push в main, при ручном запуске
и когда меняется сама инфраструктура тестов.

Как выбираются тесты:
- бэкенд: у каждого раздела есть «свои» модули app/ и свои тестовые файлы.
  Если модуль изменился, запускаются тесты его раздела и разделов всех модулей,
  которые его импортируют (граф импортов строится автоматически через ast).
  Поэтому правка codes.py запустит и тесты сканирования, и тесты лекарств
  (routers/medicines.py импортирует codes), а правка models.py — почти всё.
  Правка роутера ещё запускает интеграционные тесты, которые вызывают его эндпоинты;
- фронтенд: Vitest сам находит тесты, которые импортируют изменённые файлы
  (`vitest related`), здесь только решаем, запускать ли его вообще;
- e2e и docker-smoke запускаются целиком, если задет код, который они проверяют.

Запуск у себя: python scripts/select_tests.py --base origin/main
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = "backend/app"
TESTS = "backend/tests"

# Разделы бэкенда: «свои» модули (пути от backend/app) → тесты (пути от backend/tests).
SECTIONS: dict[str, dict[str, list[str]]] = {
    "Аккаунты и вход": {
        "sources": ["routers/auth.py", "security.py", "legal.py", "ratelimit.py", "email_verification.py", "mailer.py"],
        "tests": [
            "unit/test_security.py", "unit/test_mailer.py", "integration/test_auth.py",
            "integration/test_security_hardening.py", "integration/test_closed_mode.py",
            "integration/test_access_control.py", "integration/test_email_verification.py",
        ],
    },
    "Семьи и приглашения": {
        "sources": ["routers/families.py"],
        "tests": [
            "integration/test_families.py", "integration/test_api.py", "integration/test_access_control.py",
            "integration/test_plans.py",
        ],
    },
    "Лекарства, упаковки, остатки": {
        "sources": ["routers/medicines.py", "services.py"],
        "tests": [
            "unit/test_services.py", "integration/test_medicines.py", "integration/test_api.py",
            "integration/test_categories.py", "integration/test_intakes.py", "integration/test_access_control.py",
        ],
    },
    "История приёма лекарств": {
        "sources": ["routers/intakes.py"],
        "tests": ["integration/test_intakes.py", "integration/test_access_control.py"],
    },
    "Категории": {
        "sources": ["routers/categories.py"],
        "tests": ["integration/test_categories.py", "integration/test_access_control.py"],
    },
    "Главная, подбор по болезни, сканирование": {
        "sources": ["routers/assist.py", "search.py"],
        "tests": [
            "unit/test_search.py", "integration/test_assist.py", "integration/test_api.py",
            "integration/test_scan_lookup.py", "integration/test_access_control.py",
        ],
    },
    "Разбор кодов и поиск товара в интернете": {
        "sources": ["codes.py", "lookup.py", "websearch.py"],
        "tests": [
            "unit/test_codes.py", "unit/test_websearch.py", "integration/test_lookup.py",
            "integration/test_scan_lookup.py",
        ],
    },
    "Фото и экспорт": {
        "sources": ["routers/files.py"],
        "tests": ["integration/test_files.py", "integration/test_access_control.py"],
    },
    "Выписка для врача (PDF и Excel)": {
        "sources": ["routers/reports.py", "doctor_report.py"],
        "tests": ["integration/test_reports.py", "integration/test_access_control.py"],
    },
    "Администрирование": {
        "sources": ["routers/admin.py"],
        "tests": [
            "integration/test_admin.py", "integration/test_closed_mode.py", "integration/test_access_control.py",
            "integration/test_email_verification.py", "integration/test_plans.py",
        ],
    },
    "Тарифы: Бесплатный и Плюс": {
        "sources": ["plans.py"],
        "tests": ["integration/test_plans.py", "integration/test_access_control.py"],
    },
    "Схема базы, миграции, перенос из SQLite": {
        "sources": ["models.py", "db.py", "sqlite_import.py"],
        "tests": ["migrations/test_alembic.py", "migrations/test_sqlite_import.py"],
    },
    "Версия приложения": {
        "sources": ["version.py"],
        "tests": ["integration/test_version.py"],
    },
    # Модули, на которых держится всё приложение: их правка запускает весь бэкенд.
    "Ядро": {
        "sources": ["main.py", "config.py", "deps.py", "schemas.py", "seed.py", "__init__.py", "routers/__init__.py"],
        "tests": ["*"],
    },
}

# Правка этих файлов — повод прогнать всё: они влияют на то, как запускаются тесты.
FULL_RUN = [
    ".github/workflows/tests.yml", "scripts/select_tests.py",
    "backend/requirements.txt", "backend/requirements-dev.txt", "backend/pytest.ini",
    "backend/tests/conftest.py", "backend/tests/__init__.py",
    "frontend/package.json", "frontend/package-lock.json", "frontend/.nvmrc",
]
BACKEND_MIGRATIONS = ["backend/alembic/*", "backend/alembic.ini"]
# Фронтенд: всё, что влияет на сборку или тесты целиком (иначе Vitest сам найдёт связанные тесты).
FRONTEND_ALL = [
    "VERSION", "frontend/vitest.config.ts", "frontend/src/test/setup.ts", "frontend/vite.config.ts", "frontend/buildInfo.ts", "frontend/tsconfig.json", "frontend/index.html",
]
# Что проверяют e2e: любой код приложения и сама обвязка e2e.
E2E_TRIGGERS = [
    "backend/app/*", "backend/alembic/*", "frontend/src/*", "frontend/public/*", "frontend/index.html",
    "frontend/vite.config.ts", "frontend/buildInfo.ts", "frontend/playwright.config.ts", "frontend/e2e/*",
]
E2E_SPEC = "frontend/e2e/*.spec.ts"
# Что проверяет docker-smoke: образ, его зависимости и старт сервера.
DOCKER_TRIGGERS = [
    "Dockerfile", "VERSION", ".dockerignore", "docker-compose*.yml", "deploy/*", "backend/requirements.txt",
    "backend/alembic/*", "backend/alembic.ini", "backend/app/main.py", "backend/app/config.py",
    "frontend/package.json", "frontend/package-lock.json", "frontend/vite.config.ts", "frontend/buildInfo.ts",
    "frontend/index.html",
]


def match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def is_test_source(path: str) -> bool:
    return path.endswith((".test.ts", ".test.tsx")) or path.startswith("frontend/src/test/")


# --- граф импортов бэкенда -----------------------------------------------------

def module_name(rel: str) -> str:
    """routers/auth.py → app.routers.auth; __init__.py → app."""
    parts = ["app", *rel[:-3].split("/")]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def app_modules(root: Path = ROOT) -> dict[str, str]:
    """{имя модуля: путь от backend/app} для всех .py в приложении."""
    base = root / APP
    return {module_name(p.relative_to(base).as_posix()): p.relative_to(base).as_posix() for p in base.rglob("*.py")}


def imports_of(path: Path, module: str, known: set[str]) -> set[str]:
    """Модули приложения, которые импортирует файл (с учётом относительных импортов)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            # `from ..routers import auth` импортирует модуль app.routers.auth, а не только пакет
            names = [prefix] + [f"{prefix}.{a.name}" for a in node.names]
        else:
            continue
        found |= {n for n in names if n in known}
    found.discard(module)
    return found


def importers(root: Path = ROOT) -> dict[str, set[str]]:
    """Обратный граф: {модуль: кто его импортирует напрямую}."""
    mods = app_modules(root)
    known = set(mods)
    rev: dict[str, set[str]] = {m: set() for m in mods}
    for mod, rel in mods.items():
        for dep in imports_of(root / APP / rel, mod, known):
            rev[dep].add(mod)
    return rev


# Модули, которые только собирают приложение из роутеров: через них зависимость не распространяется,
# иначе любая правка «дотягивалась» бы до main.py и запускала всё. Их собственная правка — это «Ядро».
WIRING = {"main.py", "__init__.py", "routers/__init__.py"}


def affected_modules(changed: list[str], root: Path = ROOT) -> set[str]:
    """Изменённые модули приложения и все, кто зависит от них (транзитивно)."""
    mods = app_modules(root)
    by_path = {rel: m for m, rel in mods.items()}
    rev = importers(root)
    todo = [by_path[p[len(APP) + 1:]] for p in changed if p.startswith(APP + "/") and p[len(APP) + 1:] in by_path]
    seen: set[str] = set()
    while todo:
        m = todo.pop()
        if m not in seen:
            seen.add(m)
            todo.extend(d for d in rev.get(m, ()) if mods[d] not in WIRING)
    return {mods[m] for m in seen}


def section_of(source: str) -> list[str]:
    return [name for name, s in SECTIONS.items() if source in s["sources"]]


# --- кто вызывает эндпоинты роутера ---------------------------------------------
# Интеграционные тесты часто готовят данные через чужие эндпоинты: тест фото сначала
# создаёт лекарство, тест админки входит через /api/auth/login. Если сломать создание
# лекарства, упадёт и тест фото, поэтому такие тесты тоже запускаются. Находим их сами,
# по строкам "/api/..." в коде тестов, чтобы карту не надо было поддерживать руками.

API_CALL = re.compile(r"""["'](/api/[^"'?\s]*)""")


def router_routes(root: Path = ROOT) -> list[tuple[re.Pattern, str]]:
    """(регулярка пути, модуль роутера от backend/app) для всех эндпоинтов."""
    routes = []
    for path in sorted((root / APP / "routers").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        prefix = re.search(r'APIRouter\((?:[^)]*?)prefix="([^"]*)"', src)
        for sub in re.findall(r'@router\.\w+\(\s*"([^"]*)"', src):
            full = (prefix.group(1) if prefix else "") + sub
            template = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(full))
            routes.append((re.compile(template.rstrip("/") + "/?$"), f"routers/{path.name}"))
    return routes


def api_calls(test_path: Path) -> set[str]:
    """Пути /api/..., которые встречаются в тесте; подстановки f-строк заменены на X."""
    src = test_path.read_text(encoding="utf-8")
    # f"/api/families/{u2['families'][0]['id']}/…" обрезается на кавычке — тогда хвост неизвестен
    return {re.sub(r"\{[^}]*\}?", "X", u).rstrip("/") for u in API_CALL.findall(src)}


def callers_of(routers: set[str], root: Path = ROOT) -> set[str]:
    """Интеграционные тесты (пути от backend/tests), которые вызывают эндпоинты этих роутеров."""
    if not routers:
        return set()
    routes = [(p, r) for p, r in router_routes(root) if r in routers]
    found = set()
    for test in (root / TESTS / "integration").glob("test_*.py"):
        if any(p.match(u) for u in api_calls(test) for p, _ in routes):
            found.add(test.relative_to(root / TESTS).as_posix())
    return found


# --- выбор ---------------------------------------------------------------------

@dataclass
class Selection:
    full: bool = False
    reasons: list[str] = field(default_factory=list)
    backend: bool = False
    backend_tests: list[str] = field(default_factory=list)   # пусто при backend=True — значит все
    backend_sections: list[str] = field(default_factory=list)
    frontend: bool = False
    frontend_files: list[str] = field(default_factory=list)  # для `vitest related`; пусто — все тесты
    e2e: bool = False
    e2e_specs: list[str] = field(default_factory=list)       # пусто при e2e=True — все сценарии
    docker: bool = False


def select(changed: list[str], full: bool = False, root: Path = ROOT) -> Selection:
    s = Selection()
    full_hits = [p for p in changed if p in FULL_RUN]
    if full or full_hits:
        s.full = s.backend = s.frontend = s.e2e = s.docker = True
        s.reasons = ["полный прогон"] if full else [f"изменён {p}" for p in full_hits]
        return s

    # бэкенд
    tests: set[str] = set()
    sections: set[str] = set()
    affected = affected_modules(changed, root)
    for rel in sorted(affected):
        for name in section_of(rel):
            sections.add(name)
            tests |= set(SECTIONS[name]["tests"])
    tests |= callers_of({r for r in affected if r.startswith("routers/") and r not in WIRING}, root)
    for p in changed:
        if p.startswith(TESTS + "/") and p.endswith(".py") and Path(p).name.startswith("test_"):
            tests.add(p[len(TESTS) + 1:])
            sections.add("Изменённые тесты")
        if match(p, BACKEND_MIGRATIONS):
            tests |= set(SECTIONS["Схема базы, миграции, перенос из SQLite"]["tests"])
            sections.add("Схема базы, миграции, перенос из SQLite")
        if p.startswith(APP + "/fonts/"):  # шрифты PDF выписки для врача
            tests |= set(SECTIONS["Выписка для врача (PDF и Excel)"]["tests"])
            sections.add("Выписка для врача (PDF и Excel)")
        if p == "VERSION":  # номер версии читает version.py
            tests |= set(SECTIONS["Версия приложения"]["tests"])
            sections.add("Версия приложения")
    if tests:
        s.backend = True
        s.backend_sections = sorted(sections)
        s.backend_tests = [] if "*" in tests else sorted(tests)

    # фронтенд
    front = [p for p in changed if p.startswith("frontend/src/")]
    if any(match(p, FRONTEND_ALL) for p in changed):
        s.frontend = True
    elif front:
        s.frontend = True
        s.frontend_files = sorted(p[len("frontend/"):] for p in front)

    # e2e: если поменялись только сценарии — гоняем только их
    e2e_hits = [p for p in changed if match(p, E2E_TRIGGERS) and not is_test_source(p)]
    if e2e_hits:
        s.e2e = True
        if all(fnmatch.fnmatch(p, E2E_SPEC) for p in e2e_hits):
            s.e2e_specs = sorted(p[len("frontend/"):] for p in e2e_hits)

    s.docker = any(match(p, DOCKER_TRIGGERS) for p in changed)
    return s


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def summary(s: Selection, changed: list[str]) -> str:
    yes = lambda b: "✅ запускаем" if b else "⏭️ пропускаем"  # noqa: E731
    lines = [f"### Какие тесты запускаются ({len(changed)} изм. файлов)", ""]
    if s.full:
        lines += [f"**Полный прогон**: {', '.join(s.reasons)}", ""]
    lines += [
        f"- **Бэкенд**: {yes(s.backend)}"
        + (f" — разделы: {', '.join(s.backend_sections)}" if s.backend_sections and not s.full else ""),
        f"- **Фронтенд**: {yes(s.frontend)}"
        + (" — только тесты, связанные с изменёнными файлами" if s.frontend_files else ""),
        f"- **E2E**: {yes(s.e2e)}" + (f" — {', '.join(s.e2e_specs)}" if s.e2e_specs else ""),
        f"- **Docker smoke**: {yes(s.docker)}",
    ]
    if s.backend_tests:
        lines += ["", "<details><summary>Тестовые файлы бэкенда</summary>", "", *[f"- `{t}`" for t in s.backend_tests], "", "</details>"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="с чем сравнивать (например origin/main)")
    ap.add_argument("--full", action="store_true", help="запустить всё")
    ap.add_argument("--files", nargs="*", help="список изменённых файлов вместо git diff")
    ap.add_argument("--github-output", action="store_true", help="записать результат в $GITHUB_OUTPUT и $GITHUB_STEP_SUMMARY")
    args = ap.parse_args(argv)

    changed = args.files if args.files is not None else (changed_files(args.base) if args.base else [])
    s = select(changed, full=args.full or (args.files is None and not args.base))
    text = summary(s, changed)

    if args.github_output:
        outputs = {
            "full": str(s.full).lower(),
            "backend": str(s.backend).lower(),
            "backend_tests": " ".join(f"tests/{t}" for t in s.backend_tests),
            "frontend": str(s.frontend).lower(),
            "frontend_files": " ".join(s.frontend_files),
            "e2e": str(s.e2e).lower(),
            "e2e_specs": " ".join(s.e2e_specs),
            "docker": str(s.docker).lower(),
        }
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in outputs.items())
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(text + "\n")
    print(text)
    print("\n" + json.dumps(asdict(s), ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
