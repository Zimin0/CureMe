"""Номер версии один и тот же везде, а скрипт release.py поднимает его правильно."""

import datetime as dt
import shutil

import pytest

import release as rel


def test_version_is_the_same_everywhere():
    version = rel.read_version()
    assert rel.package_versions() == [version] * 3, "Поднимайте версию через: python scripts/release.py bump …"


def test_changelog_has_notes_for_current_version():
    assert rel.changelog_notes(rel.read_version())


@pytest.mark.parametrize("part, expected", [("patch", "1.4.3"), ("minor", "1.5.0"), ("major", "2.0.0")])
def test_next_version(part, expected):
    assert rel.next_version("1.4.2", part) == expected


def test_bump_updates_every_file(tmp_path):
    (tmp_path / "frontend").mkdir()
    for f in ["VERSION", "CHANGELOG.md", "frontend/package.json", "frontend/package-lock.json"]:
        shutil.copy(rel.ROOT / f, tmp_path / f)
    old = rel.read_version(tmp_path)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(changelog.read_text(encoding="utf-8").replace(
        rel.UNRELEASED, f"{rel.UNRELEASED}\n\n### Исправлено\n- Кнопка", 1), encoding="utf-8")

    new = rel.bump("minor", tmp_path, today=dt.date(2026, 10, 1))

    assert new == rel.next_version(old, "minor")
    assert rel.read_version(tmp_path) == new
    assert rel.package_versions(tmp_path) == [new] * 3
    text = changelog.read_text(encoding="utf-8")
    assert f"## [{new}] — 2026-10-01" in text
    # то, что уже лежит в «Не выпущено» на main, тоже переезжает в новую версию — оно идёт после
    assert rel.changelog_notes(new, tmp_path).startswith("### Исправлено\n- Кнопка")
    assert rel.changelog_notes(old, tmp_path) == rel.changelog_notes(old)  # старые записи не тронуты
    # в lock-файле версии зависимостей не задеты
    before = (rel.ROOT / "frontend/package-lock.json").read_text(encoding="utf-8").splitlines()
    after = (tmp_path / "frontend/package-lock.json").read_text(encoding="utf-8").splitlines()
    assert len(before) == len(after)
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [2, 8]
