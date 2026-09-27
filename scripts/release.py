#!/usr/bin/env python3
"""Версии приложения: поднять номер и достать заметки к релизу.

Номер версии живёт в файле VERSION (SemVer: МАЖОРНАЯ.МИНОРНАЯ.ПАТЧ) и повторяется
в frontend/package.json и package-lock.json. Этот скрипт меняет их все разом,
а в CHANGELOG.md превращает раздел «Не выпущено» в раздел новой версии.

    python scripts/release.py bump patch   # 1.0.0 → 1.0.1: исправления
    python scripts/release.py bump minor   # 1.0.0 → 1.1.0: новые возможности
    python scripts/release.py bump major   # 1.0.0 → 2.0.0: несовместимые изменения
    python scripts/release.py notes        # заметки текущей версии (для GitHub Release)

После merge в main workflow release.yml сам ставит git-тег vX.Y.Z и создаёт GitHub Release.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
UNRELEASED = "## [Не выпущено]"


def read_version(root: Path = ROOT) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.match(version):
        raise SystemExit(f"В VERSION не SemVer: {version!r}")
    return version


def next_version(version: str, part: str) -> str:
    major, minor, patch = map(int, SEMVER.match(version).groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def package_versions(root: Path = ROOT) -> list[str]:
    """Версии из package.json и package-lock.json (в lock-файле она записана дважды)."""
    pkg = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    return [pkg["version"], lock["version"], lock["packages"][""]["version"]]


def set_package_versions(root: Path, version: str) -> None:
    # Правим текстом, а не json.dump: так не меняется форматирование огромного lock-файла.
    pkg = root / "frontend/package.json"
    pkg.write_text(re.sub(r'("version": )"[^"]*"', rf'\1"{version}"', pkg.read_text(encoding="utf-8"), count=1),
                   encoding="utf-8")
    lock = root / "frontend/package-lock.json"
    text = lock.read_text(encoding="utf-8")
    # первые два "version" в lock-файле — версия самого проекта (в корне и в packages[""])
    lock.write_text(re.sub(r'("version": )"[^"]*"', rf'\1"{version}"', text, count=2), encoding="utf-8")


def changelog_notes(version: str, root: Path = ROOT) -> str:
    """Текст раздела версии из CHANGELOG.md (без заголовка)."""
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"В CHANGELOG.md нет раздела ## [{version}]")
    return m.group(1).strip()


def bump(part: str, root: Path = ROOT, today: dt.date | None = None) -> str:
    new = next_version(read_version(root), part)
    changelog = root / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    if UNRELEASED not in text:
        raise SystemExit(f"В CHANGELOG.md нет раздела «{UNRELEASED}»")
    date = (today or dt.date.today()).isoformat()
    changelog.write_text(text.replace(UNRELEASED, f"{UNRELEASED}\n\n## [{new}] — {date}", 1), encoding="utf-8")
    (root / "VERSION").write_text(new + "\n", encoding="utf-8")
    set_package_versions(root, new)
    return new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bump").add_argument("part", choices=["major", "minor", "patch"])
    sub.add_parser("notes")
    sub.add_parser("version")
    args = parser.parse_args(argv)
    if args.cmd == "bump":
        new = bump(args.part)
        print(f"Версия {new}. Допишите изменения в CHANGELOG.md и закоммитьте.")
    elif args.cmd == "notes":
        print(changelog_notes(read_version()))
    else:
        print(read_version())
    return 0


if __name__ == "__main__":
    sys.exit(main())
