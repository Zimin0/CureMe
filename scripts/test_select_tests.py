"""Тесты для выбора тестов.

Главная опасность выборочного запуска — пропустить тест, который должен был
упасть. Поэтому здесь проверяется не только логика, но и то, что карта
разделов в select_tests.py не отстала от кода:
- каждый модуль приложения и каждый тестовый файл входит в какой-то раздел;
- если тест импортирует модуль app.X, правка X запускает этот тест;
- если интеграционный тест ходит в эндпоинт, правка роутера этого эндпоинта запускает тест.
Добавили модуль, тест или эндпоинт и забыли карту — здесь станет красно.

Запуск: python -m pytest scripts -q
"""

import ast

import pytest

import select_tests as st

ROOT = st.ROOT
TEST_FILES = sorted(p.relative_to(ROOT / st.TESTS).as_posix() for p in (ROOT / st.TESTS).rglob("test_*.py"))


def backend_tests_for(changed: list[str]) -> set[str] | str:
    s = st.select(changed)
    if not s.backend:
        return set()
    return "*" if not s.backend_tests else set(s.backend_tests)


def runs(test: str, changed: list[str]) -> bool:
    sel = backend_tests_for(changed)
    return sel == "*" or test in sel


# --- карта разделов не отстала от кода -----------------------------------------

def test_every_app_module_has_a_section():
    lost = [rel for rel in st.app_modules().values() if not st.section_of(rel)]
    assert not lost, f"Добавьте эти модули в SECTIONS в scripts/select_tests.py: {lost}"


def test_every_test_file_is_in_a_section():
    listed = {t for s in st.SECTIONS.values() for t in s["tests"]}
    lost = [t for t in TEST_FILES if t not in listed]
    assert not lost, f"Эти тесты не запустятся в pull request, добавьте их в SECTIONS: {lost}"


def test_sections_point_to_existing_files():
    mods = set(st.app_modules().values())
    for name, s in st.SECTIONS.items():
        assert set(s["sources"]) <= mods, name
        assert set(s["tests"]) - {"*"} <= set(TEST_FILES), name


@pytest.mark.parametrize("test", TEST_FILES)
def test_changing_an_imported_module_runs_the_test(test):
    tree = ast.parse((ROOT / st.TESTS / test).read_text(encoding="utf-8"))
    mods = st.app_modules()
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            used |= {node.module} | {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            used |= {a.name for a in node.names}
    for mod in sorted(used & set(mods)):
        change = f"{st.APP}/{mods[mod]}"
        assert runs(test, [change]), f"{test} импортирует {mod}, но правка {change} его не запускает"


@pytest.mark.parametrize("test", [t for t in TEST_FILES if t.startswith("integration/")])
def test_changing_a_router_runs_tests_that_call_it(test):
    routes = st.router_routes()
    for url in sorted(st.api_calls(ROOT / st.TESTS / test)):
        for pattern, router in routes:
            if pattern.match(url):
                change = f"{st.APP}/{router}"
                assert runs(test, [change]), f"{test} вызывает {url}, но правка {change} его не запускает"


def test_every_router_has_routes():
    found = {r for _, r in st.router_routes()}
    routers = {rel for rel in st.app_modules().values() if rel.startswith("routers/") and rel not in st.WIRING}
    assert found == routers, "не удалось разобрать эндпоинты — поправьте router_routes()"


def test_setup_through_other_router_is_detected():
    # тест фото создаёт лекарство, тест админки входит через /api/auth/login
    assert "integration/test_files.py" in st.callers_of({"routers/medicines.py"})
    assert "integration/test_admin.py" in st.callers_of({"routers/auth.py"})
    assert "integration/test_lookup.py" not in st.callers_of({"routers/medicines.py"})


# --- логика выбора ---------------------------------------------------------------

def test_docs_only_runs_nothing():
    s = st.select(["README.md", "TESTING.md", "docs/screenshots/m-home.png"])
    assert not (s.backend or s.frontend or s.e2e or s.docker or s.full)


def test_codes_change_runs_scanning_and_medicines():
    tests = backend_tests_for(["backend/app/codes.py"])
    assert {"unit/test_codes.py", "integration/test_assist.py", "integration/test_medicines.py"} <= tests
    assert "migrations/test_alembic.py" not in tests


def test_categories_router_change_stays_narrow():
    tests = backend_tests_for(["backend/app/routers/categories.py"])
    assert "integration/test_categories.py" in tests and "integration/test_access_control.py" in tests
    assert not {"integration/test_files.py", "unit/test_codes.py", "migrations/test_alembic.py"} & tests


def test_sqlite_import_change_runs_only_its_tests():
    assert backend_tests_for(["backend/app/sqlite_import.py"]) == {"migrations/test_alembic.py", "migrations/test_sqlite_import.py"}


def test_security_change_runs_everything_through_deps():
    # deps.py (проверка входа во всех эндпоинтах) импортирует security.py, а deps.py — это «Ядро»
    assert backend_tests_for(["backend/app/security.py"]) == "*"


def test_models_change_runs_everything_backend():
    assert backend_tests_for(["backend/app/models.py"]) == "*"


def test_main_change_runs_everything_backend_but_router_change_does_not():
    assert backend_tests_for(["backend/app/main.py"]) == "*"
    assert backend_tests_for(["backend/app/routers/categories.py"]) != "*"


def test_changed_test_file_runs_itself_only():
    assert backend_tests_for(["backend/tests/unit/test_search.py"]) == {"unit/test_search.py"}
    s = st.select(["backend/tests/unit/test_search.py"])
    assert not (s.frontend or s.e2e or s.docker)


def test_migration_change_runs_migration_tests_and_docker():
    s = st.select(["backend/alembic/versions/0001_new.py"])
    assert set(s.backend_tests) == {"migrations/test_alembic.py", "migrations/test_sqlite_import.py"}
    assert s.docker and s.e2e


@pytest.mark.parametrize("path", st.FULL_RUN)
def test_infrastructure_change_runs_everything(path):
    s = st.select([path])
    assert s.full and s.backend and s.frontend and s.e2e and s.docker and not s.backend_tests


def test_frontend_source_runs_related_tests_and_e2e():
    s = st.select(["frontend/src/format.ts"])
    assert s.frontend and s.frontend_files == ["src/format.ts"] and s.e2e and not s.e2e_specs
    assert not s.backend and not s.docker


def test_frontend_test_only_skips_e2e():
    s = st.select(["frontend/src/format.test.ts", "frontend/src/test/utils.tsx"])
    assert s.frontend and not s.e2e


def test_frontend_config_runs_all_frontend_tests():
    s = st.select(["frontend/vitest.config.ts"])
    assert s.frontend and s.frontend_files == []


def test_e2e_spec_only_runs_that_spec():
    s = st.select(["frontend/e2e/scan.spec.ts"])
    assert s.e2e and s.e2e_specs == ["e2e/scan.spec.ts"] and not s.frontend and not s.backend


def test_e2e_helper_change_runs_all_specs():
    s = st.select(["frontend/e2e/scan.spec.ts", "frontend/e2e/helpers.ts"])
    assert s.e2e and s.e2e_specs == []


def test_dockerfile_runs_only_docker():
    s = st.select(["Dockerfile"])
    assert s.docker and not (s.backend or s.frontend or s.e2e)


def test_explicit_full_run():
    s = st.select([], full=True)
    assert s.full and s.backend and s.backend_tests == []


def test_module_names():
    assert st.module_name("routers/auth.py") == "app.routers.auth"
    assert st.module_name("__init__.py") == "app"
    assert st.module_name("routers/__init__.py") == "app.routers"


def test_relative_imports_are_resolved():
    rev = st.importers()
    assert "app.routers.families" in rev["app.routers.auth"]   # from .auth import create_family
    assert "app.routers.medicines" in rev["app.codes"]          # from ..codes import parse_code
    assert "app.main" in rev["app.routers.admin"]               # from .routers import admin, ...


def test_version_bump_runs_version_checks_frontend_and_docker():
    s = st.select(["VERSION"])
    assert s.backend and s.backend_tests == ["integration/test_version.py"]
    assert s.frontend and not s.frontend_files and s.docker


def test_pdf_font_change_runs_report_tests():
    s = st.select(["backend/app/fonts/DejaVuSans.ttf"])
    assert s.backend and "integration/test_reports.py" in s.backend_tests
