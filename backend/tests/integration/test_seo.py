"""SEO: мета-теги публичных страниц, robots.txt, sitemap.xml."""

import pytest

from app import seo

pytestmark = pytest.mark.integration

TEMPLATE = (
    '<html><head><title>old</title><meta name="description" content="old" /></head>'
    '<body><div id="root"></div></body></html>'
)
BASE = "https://kapsulka.ru"


def test_home_has_meta_canonical_jsonld_and_text():
    out = seo.render_index(TEMPLATE, "/", BASE)
    assert out.count("<title>") == 1 and "old" not in out
    assert '<link rel="canonical" href="https://kapsulka.ru/" />' in out
    assert 'content="index, follow"' in out
    assert 'property="og:title"' in out and "application/ld+json" in out
    assert "<h1>Домашняя аптечка" in out  # текст виден поисковику без JS


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/consent"])
def test_legal_pages_indexable_with_own_canonical(path):
    out = seo.render_index(TEMPLATE, path, BASE)
    assert f'href="{BASE}{path}"' in out and "index, follow" in out
    assert "<h1>" not in out


@pytest.mark.parametrize("path", ["/medicines", "/admin", "/login", "/nope"])
def test_private_pages_noindex(path):
    out = seo.render_index(TEMPLATE, path, BASE)
    assert "noindex" in out and "canonical" not in out


def test_robots_and_sitemap(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Disallow: /api/" in r.text and "Sitemap: " in r.text and "/sitemap.xml" in r.text
    s = client.get("/sitemap.xml")
    assert s.status_code == 200 and "xml" in s.headers["content-type"]
    for p in ("/", "/privacy", "/terms", "/consent"):
        assert f"{p}</loc>" in s.text
    assert "/admin" not in s.text


def test_verification_meta_only_on_home():
    v = {"yandex-verification": "abc123", "google-site-verification": ""}
    assert '<meta name="yandex-verification" content="abc123" />' in seo.render_index(TEMPLATE, "/", BASE, v)
    assert "google-site-verification" not in seo.render_index(TEMPLATE, "/", BASE, v)
    assert "yandex-verification" not in seo.render_index(TEMPLATE, "/terms", BASE, v)
