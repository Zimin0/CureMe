"""Кеш: оболочка приложения проверяется на сервере, файлы с хешем кешируются навсегда."""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("path", ["/sw.js", "/registerSW.js", "/manifest.webmanifest", "/", "/medicines"])
def test_app_shell_is_revalidated(client, path):
    assert client.get(path).headers["cache-control"] == "no-cache"


def test_hashed_assets_are_immutable(client):
    assert "immutable" in client.get("/assets/index-abc123.js").headers["cache-control"]


def test_api_is_never_cached(client):
    assert client.get("/api/health").headers["cache-control"] == "no-store"
