"""Версия приложения: файл VERSION и эндпоинт /api/version."""

import pytest

from app import version as v


@pytest.fixture(autouse=True)
def fresh_cache():
    v.app_version.cache_clear()
    yield
    v.app_version.cache_clear()


def test_version_file_is_semver():
    assert v.SEMVER.match(v.read_version()), "В VERSION должна быть версия вида 1.2.3"


def test_bad_or_missing_version_file_falls_back(tmp_path):
    assert v.read_version(tmp_path / "нет") == "0.0.0"
    bad = tmp_path / "VERSION"
    bad.write_text("первая\n", encoding="utf-8")
    assert v.read_version(bad) == "0.0.0"
    bad.write_text("2.3.4\n", encoding="utf-8")
    assert v.read_version(bad) == "2.3.4"


def test_version_endpoint_is_public_and_shows_build(client, monkeypatch):
    monkeypatch.setenv("CUREME_COMMIT", "abc1234")
    monkeypatch.setenv("CUREME_BUILT_AT", "2026-09-27T21:00:00Z")
    r = client.get("/api/version")  # без входа: версию смотрят и при проблемах со входом
    assert r.status_code == 200
    assert r.json() == {"version": v.read_version(), "commit": "abc1234", "built_at": "2026-09-27T21:00:00Z"}


def test_local_run_has_no_commit(client, monkeypatch):
    monkeypatch.delenv("CUREME_COMMIT", raising=False)
    monkeypatch.delenv("CUREME_BUILT_AT", raising=False)
    assert client.get("/api/version").json()["commit"] is None
