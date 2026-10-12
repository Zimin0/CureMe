"""Собственная статистика: заходы считаются без cookie, IP и кодов, отчёт видит только админ."""
from tests.conftest import register


def visit(client, **body):
    return client.post("/api/stats/visit", json=body)


def test_visit_is_counted_without_cookies_or_personal_data(client):
    r = visit(client, path="/plus?x=1", ref="https://www.yandex.ru/search?text=секрет", utm="Telegram_Mama")
    assert r.status_code == 204 and not r.cookies and "set-cookie" not in r.headers
    visit(client, path="/join/SECRETCODE")
    visit(client, path="/medicines/42")
    h, _ = register(client)
    rep = client.get("/api/admin/site-stats?days=7", headers=h).json()
    assert rep["totals"]["visits"] == 3
    pages = {p["key"]: p["count"] for p in rep["pages"]}
    assert pages == {"/plus": 1, "/join": 1, "/app": 1}  # ни кода приглашения, ни номера лекарства
    assert rep["sources"] == [{"key": "yandex.ru", "count": 1}]  # только домен, без запроса
    assert rep["utm"] == [{"key": "telegram_mama", "count": 1}]
    assert rep["totals"]["registrations"] == 1


def test_junk_referrer_utm_and_own_site_are_dropped(client):
    visit(client, path="/", ref="javascript:alert(1)", utm="<script>")
    visit(client, path="/", ref="http://testserver/login")
    h, _ = register(client)
    rep = client.get("/api/admin/site-stats", headers=h).json()
    assert rep["sources"] == [] and rep["utm"] == [] and rep["totals"]["visits"] == 2


def test_goals_are_whitelisted(client):
    client.post("/api/stats/goal", json={"goal": "plus_view"})
    client.post("/api/stats/goal", json={"goal": "<script>"})
    h, _ = register(client)
    t = client.get("/api/admin/site-stats", headers=h).json()["totals"]
    assert t["plus_view"] == 1 and t["pay_click"] == 0


def test_report_is_admin_only(client):
    register(client)  # первый аккаунт — админ
    h2, _ = register(client, email="two@example.com", name="Два")
    assert client.get("/api/admin/site-stats", headers=h2).status_code == 403
    assert client.get("/api/admin/site-stats").status_code in (401, 403)
