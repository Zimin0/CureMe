"""Оплата Плюса через ЮKassa.

Как это устроено:
- Карту вводят в виджете ЮKassa на нашей странице: номер карты до нашего сервера не доходит (мы получаем
  только confirmation_token для виджета и потом идентификатор сохранённого способа оплаты).
- Что оплата прошла, мы узнаём не из браузера, а от ЮKassa: приходит HTTP-уведомление (webhook), и мы
  сами запрашиваем платёж по его id с нашим секретным ключом. Поддельное уведомление ничего не даст:
  статус берём только из ответа ЮKassa. Повторное уведомление безопасно (операция идемпотентна).
- Автопродление: за 3 дня до окончания Плюса уходит письмо, в день окончания списываем по сохранённому
  способу оплаты. Включается только галочкой при оплате, выключается кнопкой на странице «Плюс».
- Чек самозанятого (422-ФЗ) ЮKassa выпустить не может: админ оформляет его в «Мой налог» и вставляет ссылку
  на странице «Оплаты и чеки», письмо с ссылкой уходит покупателю.
Пока в .env нет CUREME_YOOKASSA_SHOP_ID и CUREME_YOOKASSA_SECRET_KEY, всё выключено.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .mailer import send_mail
from .models import Payment, User
from .plans import PLUS, billing_settings, plus_active

log = logging.getLogger("cureme.payments")
API = "https://api.yookassa.ru/v3"
PERIOD_DAYS = {"month": 30, "year": 365}
PERIOD_TITLE = {"month": "1 месяц", "year": "1 год"}
NOTICE_DAYS = 3  # за сколько дней предупреждаем о списании
RETRY_HOURS = 2  # письмо должно уйти не позже чем за 3 дня минус эта погрешность


class PaymentError(Exception):
    """Платёжный сервис недоступен или отказал."""


def configured() -> bool:
    return get_settings().yookassa_enabled


def recurring_enabled() -> bool:
    return configured() and get_settings().yookassa_recurring


def price_for(db: Session, period: str) -> int | None:
    b = billing_settings(db)
    return b.price_month if period == "month" else b.price_year


def payments_enabled(db: Session) -> bool:
    """Оплата открыта: ключи ЮKassa в .env, платная версия включена, цена задана."""
    b = billing_settings(db)
    return configured() and b.enabled and bool(b.price_month or b.price_year)


def _request(method: str, path: str, *, key: str | None = None, json: dict | None = None) -> dict:
    s = get_settings()
    headers = {"Idempotence-Key": key} if key else {}
    try:
        r = httpx.request(method, f"{API}{path}", json=json, headers=headers, timeout=15,
                          auth=(s.yookassa_shop_id, s.yookassa_secret_key))
    except httpx.HTTPError as e:
        raise PaymentError("Платёжный сервис не отвечает") from e
    if r.status_code >= 400:
        log.error("ЮKassa %s %s: %s %s", method, path, r.status_code, r.text[:300])
        raise PaymentError(_error_text(r, bool(json and json.get("save_payment_method"))))
    return r.json()


def _error_text(r: httpx.Response, wanted_autopay: bool) -> str:
    """Понятное сообщение об отказе ЮKassa: код ошибки и, если вероятна причина, подсказка."""
    try:
        code = r.json().get("code") or ""
    except ValueError:
        code = ""
    text = f"ЮKassa отказала ({r.status_code}{', ' + code if code else ''})"
    if r.status_code == 403 and wanted_autopay:
        text += ". Возможно, в ЮKassa не подключены автоплатежи: попробуйте без галочки автопродления"
    elif r.status_code in (401, 403):
        text += ". Проверьте ключи ЮKassa и права магазина"
    return text


def _amount(rub: int) -> dict:
    return {"value": f"{rub}.00", "currency": "RUB"}


def _description(user: User, period: str) -> str:
    return f"Подписка Капсулка Плюс на {PERIOD_TITLE[period]}, аккаунт {user.email}"[:128]


def create_payment(db: Session, user: User, period: str, auto_renew: bool) -> tuple[Payment, str]:
    """Создаёт платёж с виджетом ЮKassa. Возвращает запись и confirmation_token для виджета."""
    amount = price_for(db, period)
    if not amount:
        raise PaymentError("Для этого срока цена не задана")
    pay = Payment(user_id=user.id, email=user.email, period=period, amount=amount)
    db.add(pay)
    db.flush()
    body = {
        "amount": _amount(amount),
        "capture": True,
        "confirmation": {"type": "embedded"},
        "description": _description(user, period),
        "metadata": {"payment_id": str(pay.id), "user_id": str(user.id), "period": period},
    }
    if auto_renew:
        body["save_payment_method"] = True
    data = _request("POST", "/payments", key=f"pay-{pay.id}", json=body)
    pay.yk_id = data["id"]
    if auto_renew:
        # Пока платёж не прошёл, автопродление не включаем; помним выбор в metadata ЮKassa и здесь:
        user.renew_period = period
    db.commit()
    return pay, data["confirmation"]["confirmation_token"]


def extend_plus(user: User, period: str, now: datetime | None = None) -> None:
    """Продлевает Плюс: от конца текущего срока, если он ещё идёт, иначе от сегодняшнего дня."""
    now = now or datetime.now(timezone.utc)
    base = now
    if plus_active(user) and user.plus_until is not None:
        until = user.plus_until if user.plus_until.tzinfo else user.plus_until.replace(tzinfo=timezone.utc)
        base = max(now, until)
    user.plan = PLUS
    user.plus_until = base + timedelta(days=PERIOD_DAYS[period])


def sync_payment(db: Session, yk_id: str) -> Payment | None:
    """Запрашивает платёж у ЮKassa и приводит нашу запись в соответствие. Безопасно вызывать повторно."""
    data = _request("GET", f"/payments/{yk_id}")
    pay = db.scalar(select(Payment).where(Payment.yk_id == yk_id))
    if pay is None:
        pid = (data.get("metadata") or {}).get("payment_id")
        pay = db.get(Payment, int(pid)) if pid and str(pid).isdigit() else None
        if pay is None:
            return None
        pay.yk_id = yk_id
    # Сумму сверяем с тем, что мы создавали: оплата другой суммы Плюс не открывает.
    paid_rub = data.get("amount", {}).get("value")
    status = data.get("status")
    user = db.get(User, pay.user_id) if pay.user_id else None
    if status == "succeeded" and pay.status == "pending":
        if paid_rub is not None and int(float(paid_rub)) != pay.amount:
            log.error("Платёж %s: сумма %s не совпадает с %s, Плюс не выдан", yk_id, paid_rub, pay.amount)
        else:
            pay.status = "succeeded"
            pay.paid_at = datetime.now(timezone.utc)
            if user:
                extend_plus(user, pay.period, pay.paid_at)
                method = data.get("payment_method") or {}
                if method.get("saved") and method.get("id") and not pay.recurring:
                    user.auto_renew = True
                    user.pay_method_id = method["id"]
                    user.renew_period = pay.period
                user.renew_notified_for = None
    elif status == "canceled" and pay.status == "pending":
        pay.status = "canceled"
        if pay.recurring and user:
            _renewal_failed(user)
    if pay.status == "succeeded" and float(data.get("refunded_amount", {}).get("value", 0) or 0) > 0:
        pay.status = "refunded"
        if user:
            user.auto_renew = False
            user.pay_method_id = None
    db.commit()
    return pay


def _site() -> str:
    return (get_settings().public_url or "https://kapsulka.ru").rstrip("/")


def _renewal_failed(user: User) -> None:
    user.auto_renew = False
    user.pay_method_id = None
    send_mail(
        user.email, "Капсулка: не удалось продлить Плюс",
        f"Здравствуйте, {user.name}!\n\nНе удалось списать оплату за продление Капсулка Плюс, автопродление отключено. "
        f"Деньги не списаны. Продлить подписку можно на странице {_site()}/plus.\n\nКапсулка",
    )


def _next_price(db: Session, user: User) -> int | None:
    return price_for(db, user.renew_period or "month")


def run_renewals(db: Session, now: datetime | None = None) -> None:
    """Раз в минуту из фонового потока: письмо за 3 дня и списание в день окончания."""
    if not configured():
        return
    now = now or datetime.now(timezone.utc)
    users = db.scalars(select(User).where(User.auto_renew.is_(True), User.pay_method_id.is_not(None), User.plus_until.is_not(None)))
    for user in list(users):
        until = user.plus_until if user.plus_until.tzinfo else user.plus_until.replace(tzinfo=timezone.utc)
        notified_for = user.renew_notified_for
        if notified_for is not None and notified_for.tzinfo is None:
            notified_for = notified_for.replace(tzinfo=timezone.utc)
        notified = notified_for == until
        price = _next_price(db, user)
        if not price:
            continue
        if not notified and now >= until - timedelta(days=NOTICE_DAYS) and now < until:
            _notify(db, user, until, price, now)
        elif notified and now >= until:
            at = user.renew_notified_at if user.renew_notified_at.tzinfo else user.renew_notified_at.replace(tzinfo=timezone.utc)
            if until - at < timedelta(days=NOTICE_DAYS) - timedelta(hours=RETRY_HOURS):
                # Письмо ушло позже чем за 3 дня: списывать нельзя, отключаем автопродление
                log.warning("Автопродление пользователя %s отключено: предупреждение пришло менее чем за 3 дня", user.id)
                user.auto_renew = False
                user.pay_method_id = None
                db.commit()
                continue
            _charge(db, user, price, until)


def _notify(db: Session, user: User, until: datetime, price: int, now: datetime) -> None:
    date = until.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
    ok = send_mail(
        user.email, "Капсулка: скоро спишем оплату за Плюс",
        f"Здравствуйте, {user.name}!\n\nЧерез {NOTICE_DAYS} дня, {date}, подписка Капсулка Плюс продлится автоматически: "
        f"с вашей карты будет списано {price} ₽ за {PERIOD_TITLE[user.renew_period or 'month']}.\n\n"
        f"Чтобы отказаться, нажмите «Отключить автопродление» на странице {_site()}/plus. Тогда деньги не спишутся, "
        f"Плюс закончится {date}.\n\nКапсулка",
    )
    if ok:
        user.renew_notified_for = until
        user.renew_notified_at = now
        db.commit()


def _charge(db: Session, user: User, price: int, until: datetime) -> None:
    period = user.renew_period or "month"
    key = f"renew-{user.id}-{int(until.timestamp())}"
    pay = db.scalar(select(Payment).where(Payment.user_id == user.id, Payment.recurring.is_(True), Payment.yk_id == key))
    if pay is not None:
        return  # уже пробовали для этого срока
    pay = Payment(user_id=user.id, email=user.email, period=period, amount=price, recurring=True, yk_id=None)
    db.add(pay)
    db.flush()
    try:
        data = _request("POST", "/payments", key=key, json={
            "amount": _amount(price), "capture": True, "payment_method_id": user.pay_method_id,
            "description": _description(user, period),
            "metadata": {"payment_id": str(pay.id), "user_id": str(user.id), "period": period},
        })
        pay.yk_id = data["id"]
        db.commit()
        sync_payment(db, data["id"])
    except PaymentError:
        pay.status = "canceled"
        pay.yk_id = key  # чтобы не повторять попытку каждую минуту
        _renewal_failed(user)
        db.commit()
