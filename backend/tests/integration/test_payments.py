"""Оплата Плюса через ЮKassa: сеть подменяем, проверяем нашу логику (webhook, продление, чеки, автопродление)."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer, payments
from app.config import get_settings
from app.models import Payment, User
from tests.conftest import register


@pytest.fixture
def yk(monkeypatch):
    """Ключи ЮKassa заданы, платная версия включена, цена 199/1990. Возвращает «сервер ЮKassa»."""
    s = get_settings()
    monkeypatch.setattr(s, "yookassa_shop_id", "1480957")
    monkeypatch.setattr(s, "yookassa_secret_key", "test-secret")

    class Fake:
        def __init__(self):
            self.calls, self.objects = [], {}
            self.fail = False

        def request(self, method, path, key=None, json=None):
            self.calls.append((method, path, key, json))
            if self.fail:
                raise payments.PaymentError("down")
            if method == "POST":
                n = len(self.objects) + 1
                obj = {"id": f"yk-{n}", "status": "pending", "amount": json["amount"], "metadata": json["metadata"],
                       "confirmation": {"confirmation_token": f"tok-{n}"}}
                if "payment_method_id" in json:
                    obj["status"] = "succeeded"
                self.objects[obj["id"]] = obj
                return obj
            return self.objects[path.rsplit("/", 1)[1]]

    fake = Fake()
    monkeypatch.setattr(payments, "_request", fake.request)
    return fake


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(payments, "send_mail", lambda to, subj, text, html=None: sent.append((to, subj, text)) or True)
    monkeypatch.setattr(mailer, "send_mail", lambda to, subj, text, html=None: sent.append((to, subj, text)) or True)
    monkeypatch.setattr("app.routers.admin.send_mail", lambda to, subj, text, html=None: sent.append((to, subj, text)) or True)
    return sent


@pytest.fixture
def shop(client, yk):
    h, u = register(client)  # первый аккаунт — админ
    r = client.put("/api/admin/billing", headers=h, json={"enabled": True, "price_month": 199, "price_year": 1990, "trial_days": 0})
    assert r.status_code == 200
    return h, u


def pay(client, h, period="month", auto_renew=False, agree=True):
    return client.post("/api/payments", headers=h, json={"period": period, "auto_renew": auto_renew, "agree": agree})


def user_row(session_factory, uid):
    with session_factory() as db:
        return db.get(User, uid)


def test_payments_off_without_keys(client):
    h, _ = register(client)
    client.put("/api/admin/billing", headers=h, json={"enabled": True, "price_month": 199})
    assert client.get("/api/payments/me", headers=h).json()["enabled"] is False
    assert pay(client, h).status_code == 409
    assert client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "x"}}).status_code == 404


def test_payments_off_while_billing_off(client, yk):
    h, _ = register(client)
    assert client.get("/api/payments/me", headers=h).json()["enabled"] is False
    assert pay(client, h).status_code == 409


def test_checkout_requires_agreement(client, shop):
    h, _ = shop
    assert pay(client, h, agree=False).status_code == 422
    assert client.post("/api/payments", headers=h, json={"period": "month"}).status_code == 422
    assert pay(client, h, period="week").status_code == 422


def test_create_payment_sends_amount_no_card_data(client, shop, yk):
    h, _ = shop
    r = pay(client, h, "year")
    assert r.status_code == 201 and r.json()["confirmation_token"] == "tok-1"
    method, path, key, body = yk.calls[0]
    assert (method, path) == ("POST", "/payments") and key.startswith("pay-")
    assert body["amount"] == {"value": "1990.00", "currency": "RUB"}
    assert body["confirmation"] == {"type": "embedded"} and "save_payment_method" not in body


def test_webhook_activates_plus_once(client, shop, yk, session_factory):
    h, u = shop
    pay(client, h)
    yk.objects["yk-1"]["status"] = "succeeded"
    hook = {"event": "payment.succeeded", "object": {"id": "yk-1"}}
    assert client.post("/api/payments/yookassa/webhook", json=hook).status_code == 200
    first = user_row(session_factory, u["id"]).plus_until
    assert client.post("/api/payments/yookassa/webhook", json=hook).status_code == 200  # повтор уведомления
    row = user_row(session_factory, u["id"])
    assert row.plan == "plus" and row.plus_until == first
    left = first.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=29) < left <= timedelta(days=30)
    me = client.get("/api/payments/me", headers=h).json()
    assert me["payments"][0]["status"] == "succeeded" and me["plus_active"] is True


def test_second_payment_extends_from_current_end(client, shop, yk, session_factory):
    h, u = shop
    for _ in range(2):
        pay(client, h)
        pid = f"yk-{len(yk.objects)}"
        yk.objects[pid]["status"] = "succeeded"
        client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": pid}})
    left = user_row(session_factory, u["id"]).plus_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=59) < left <= timedelta(days=60)


def test_webhook_is_not_trusted_without_yookassa_confirmation(client, shop, yk, session_factory):
    h, u = shop
    pay(client, h)  # платёж остался pending на стороне ЮKassa
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1"}})
    assert user_row(session_factory, u["id"]).plan == "free"
    assert client.post("/api/payments/yookassa/webhook", json={"nonsense": 1}).status_code == 400


def test_wrong_amount_does_not_give_plus(client, shop, yk, session_factory):
    h, u = shop
    pay(client, h)
    yk.objects["yk-1"].update(status="succeeded", amount={"value": "1.00", "currency": "RUB"})
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1"}})
    assert user_row(session_factory, u["id"]).plan == "free"


def test_webhook_asks_again_when_yookassa_down(client, shop, yk):
    h, _ = shop
    pay(client, h)
    yk.fail = True
    assert client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1"}}).status_code == 503


def test_canceled_payment(client, shop, yk, session_factory):
    h, u = shop
    pay(client, h)
    yk.objects["yk-1"]["status"] = "canceled"
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.canceled", "object": {"id": "yk-1"}})
    assert client.get("/api/payments/me", headers=h).json()["payments"][0]["status"] == "canceled"
    assert user_row(session_factory, u["id"]).plan == "free"


def test_refund_marks_payment_and_stops_autorenew(client, shop, yk, session_factory):
    h, u = shop
    pay(client, h, auto_renew=True)
    yk.objects["yk-1"].update(status="succeeded", payment_method={"saved": True, "id": "pm-1"})
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1"}})
    assert user_row(session_factory, u["id"]).auto_renew is True
    yk.objects["yk-1"]["refunded_amount"] = {"value": "199.00", "currency": "RUB"}
    client.post("/api/payments/yookassa/webhook", json={"event": "refund.succeeded", "object": {"id": "r-1", "payment_id": "yk-1"}})
    row = user_row(session_factory, u["id"])
    assert row.auto_renew is False and row.pay_method_id is None
    assert client.get("/api/payments/me", headers=h).json()["payments"][0]["status"] == "refunded"


def test_autorenew_is_opt_in_and_can_be_switched_off(client, shop, yk, session_factory):
    h, u = shop
    pay(client, h)  # галочка не стояла
    assert "save_payment_method" not in yk.calls[0][3]
    yk.objects["yk-1"].update(status="succeeded", payment_method={"saved": False})
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-1"}})
    assert user_row(session_factory, u["id"]).auto_renew is False
    pay(client, h, auto_renew=True)
    assert yk.calls[-1][3]["save_payment_method"] is True
    yk.objects["yk-2"].update(status="succeeded", payment_method={"saved": True, "id": "pm-9"})
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "yk-2"}})
    assert client.get("/api/payments/me", headers=h).json()["auto_renew"] is True
    r = client.post("/api/payments/auto-renew/off", headers=h)
    assert r.json()["auto_renew"] is False
    row = user_row(session_factory, u["id"])
    assert row.pay_method_id is None and row.auto_renew is False


def _autorenew_user(client, session_factory, yk, until_in):
    h, u = register(client, "buyer@example.com", "Покупатель")
    with session_factory() as db:
        user = db.get(User, u["id"])
        user.plan, user.plus_until = "plus", datetime.now(timezone.utc) + until_in
        user.auto_renew, user.pay_method_id, user.renew_period = True, "pm-1", "month"
        db.commit()
    return u["id"]


def test_renewal_notice_three_days_then_charge(client, shop, yk, outbox, session_factory):
    uid = _autorenew_user(client, session_factory, yk, timedelta(days=2, hours=23))
    with session_factory() as db:
        payments.run_renewals(db)
    assert len(outbox) == 1 and "спишем" in outbox[0][1] and "199" in outbox[0][2] and "Отключить автопродление" in outbox[0][2]
    assert not [c for c in yk.calls if c[3] and "payment_method_id" in c[3]]  # деньги пока не списаны
    with session_factory() as db:
        payments.run_renewals(db)  # повторный проход письмо не дублирует
    assert len(outbox) == 1


def test_charge_only_after_due_and_notice(client, shop, yk, outbox, session_factory):
    uid = _autorenew_user(client, session_factory, yk, timedelta(days=3))
    with session_factory() as db:
        payments.run_renewals(db)
        user = db.get(User, uid)
        assert user.renew_notified_for is not None
        # Прошло три дня: срок вышел, предупреждение было вовремя
        user.renew_notified_at = datetime.now(timezone.utc) - timedelta(days=3)
        user.plus_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        user.renew_notified_for = user.plus_until
        db.commit()
        payments.run_renewals(db)
        charge = [c for c in yk.calls if c[3] and "payment_method_id" in c[3]]
        assert len(charge) == 1 and charge[0][3]["payment_method_id"] == "pm-1"
        assert db.get(User, uid).plus_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(days=29)
        payments.run_renewals(db)  # повторно для того же срока не списываем
        assert len([c for c in yk.calls if c[3] and "payment_method_id" in c[3]]) == 1


def test_no_charge_if_notice_was_late(client, shop, yk, outbox, session_factory):
    uid = _autorenew_user(client, session_factory, yk, timedelta(hours=5))
    with session_factory() as db:
        payments.run_renewals(db)  # письмо ушло за 5 часов, а не за 3 дня
        user = db.get(User, uid)
        user.plus_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        user.renew_notified_for = user.plus_until
        db.commit()
        payments.run_renewals(db)
        user = db.get(User, uid)
        assert user.auto_renew is False
        assert not [c for c in yk.calls if c[3] and "payment_method_id" in c[3]]


def test_failed_charge_turns_autorenew_off_and_tells_user(client, shop, yk, outbox, session_factory):
    uid = _autorenew_user(client, session_factory, yk, timedelta(days=3))
    with session_factory() as db:
        payments.run_renewals(db)
        user = db.get(User, uid)
        user.renew_notified_at = datetime.now(timezone.utc) - timedelta(days=3)
        user.plus_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        user.renew_notified_for = user.plus_until
        db.commit()
        yk.fail = True
        payments.run_renewals(db)
        assert db.get(User, uid).auto_renew is False
    assert any("не удалось продлить" in m[1] for m in outbox)


# --- админка: список оплат и чеки ---
def _paid(client, h, yk):
    pay(client, h)
    pid = f"yk-{len(yk.objects)}"
    yk.objects[pid]["status"] = "succeeded"
    client.post("/api/payments/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": pid}})
    return next(p for p in client.get("/api/admin/payments", headers=h).json() if p["status"] == "succeeded")


def test_admin_payments_list_and_receipt_email(client, shop, yk, outbox):
    h, u = shop
    p = _paid(client, h, yk)
    assert p["email"] == u["email"] and p["amount"] == 199 and p["receipt_url"] is None and p["receipt_sent_at"] is None
    url = "https://lknpd.nalog.ru/api/v1/receipt/470418719903/abc/print"
    r = client.put(f"/api/admin/payments/{p['id']}/receipt", headers=h, json={"url": url})
    assert r.status_code == 200 and r.json()["receipt_url"] == url and r.json()["receipt_sent_at"]
    assert outbox[-1][0] == u["email"] and url in outbox[-1][2]
    r = client.delete(f"/api/admin/payments/{p['id']}/receipt", headers=h)
    assert r.json()["receipt_url"] is None and r.json()["receipt_sent_at"] is None


def test_receipt_only_for_paid_and_only_https(client, shop, yk, outbox):
    h, _ = shop
    pay(client, h)  # ещё не оплачен
    pending = client.get("/api/admin/payments", headers=h).json()[0]
    ok = "https://lknpd.nalog.ru/x/print"
    assert client.put(f"/api/admin/payments/{pending['id']}/receipt", headers=h, json={"url": ok}).status_code == 409
    p = _paid(client, h, yk)
    for bad in ("http://lknpd.nalog.ru/x/print", "javascript:alert(1)", "not a url at all"):
        assert client.put(f"/api/admin/payments/{p['id']}/receipt", headers=h, json={"url": bad}).status_code == 422
    assert client.put("/api/admin/payments/9999/receipt", headers=h, json={"url": ok}).status_code == 404


def test_receipt_without_email_only_saves_link(client, shop, yk, outbox):
    h, _ = shop
    p = _paid(client, h, yk)
    before = len(outbox)
    r = client.put(f"/api/admin/payments/{p['id']}/receipt", headers=h, json={"url": "https://lknpd.nalog.ru/x/print", "send_email": False})
    assert r.json()["receipt_url"] and r.json()["receipt_sent_at"] is None and len(outbox) == before


def test_payments_admin_only(client, shop, yk):
    h, _ = shop
    other, _ = register(client, "other@example.com")
    assert client.get("/api/admin/payments", headers=other).status_code == 403
    assert client.put("/api/admin/payments/1/receipt", headers=other, json={"url": "https://x.example/aaaa"}).status_code == 403
    assert client.get("/api/payments/me").status_code == 401
