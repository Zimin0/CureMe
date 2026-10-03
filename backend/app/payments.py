"""Оплата Плюса через ЮKassa.

Как это устроено:
- Карту вводят на странице оплаты ЮKassa: номер карты до нашего сервера не доходит (мы получаем
  только адрес страницы оплаты и потом идентификатор сохранённого способа оплаты).
- Что оплата прошла, мы узнаём не из браузера, а от ЮKassa: приходит HTTP-уведомление (webhook), и мы
  сами запрашиваем платёж по его id с нашим секретным ключом. Поддельное уведомление ничего не даст:
  статус берём только из ответа ЮKassa. Повторное уведомление безопасно (операция идемпотентна).
- Платит только владелец семьи (R06), а Плюс продлевается семье: платёж помнит семью (payments.household_id),
  и по уведомлению срок получает она, даже если владелец с тех пор сменился. Возврат закрывает Плюс семьи сразу (R15).
- Автопродление (одна карта на семью, карта владельца, R21): за 3 дня до окончания Плюса уходит письмо, в день
  окончания списываем по сохранённому способу оплаты. Включается только галочкой при оплате, выключается кнопкой на странице «Плюс».
- Чек самозанятого (422-ФЗ) ЮKassa выпустить не может: админ оформляет его в «Мой налог» и вставляет ссылку
  на странице «Оплаты и чеки», письмо с ссылкой уходит покупателю.
Пока в .env нет CUREME_YOOKASSA_SHOP_ID и CUREME_YOOKASSA_SECRET_KEY, всё выключено.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from . import compression
from .households import owner_of, stop_autorenew
from .mailer import send_mail
from .models import Household, Payment, User
from .plans import MAX_AHEAD_MONTHS, PLUS, billing_settings, plus_active
from .plans import shift_months as _shift_months

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


def _msk_date(moment: datetime) -> str:
    return moment.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")


def _new_end(house: Household, period: str, now: datetime) -> datetime:
    """Когда закончится Плюс семьи, если сейчас продлить его на период: от конца идущего срока, иначе от сегодня."""
    until = _until(house)
    base = max(now, until) if plus_active(house) and until is not None else now
    return base + timedelta(days=PERIOD_DAYS[period])


def check_can_pay(user: User, period: str, now: datetime | None = None) -> Household:
    """Может ли человек сейчас оплатить Плюс своей семье (R06). Возвращает семью или отказывает с понятным текстом."""
    now = now or datetime.now(timezone.utc)
    house = user.household
    owner = owner_of(house)
    if house is None or owner is None or owner.id != user.id:
        who = f": {owner.name}" if owner is not None else ""
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            f"Плюс оплачивает владелец семьи{who}. Хотите платить сами, попросите передать вам владение.",
        )
    if house.plan == PLUS and house.plus_until is None:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "У вашей семьи Плюс без ограничения срока, оплачивать его не нужно.")
    new_end, limit = _new_end(house, period, now), _shift_months(now, MAX_AHEAD_MONTHS)
    if new_end > limit:
        until = _until(house)
        text = f"Плюс уже оплачен до {_msk_date(until)}" if until is not None else "Плюс уже оплачен"
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"{text}: вперёд можно оплатить не больше чем на {MAX_AHEAD_MONTHS} месяцев. "
            f"Этот срок можно будет оплатить с {_msk_date(_shift_months(new_end, -MAX_AHEAD_MONTHS))}.",
        )
    return house


def create_payment(db: Session, user: User, period: str, auto_renew: bool) -> tuple[Payment, str]:
    """Создаёт платёж ЮKassa на семью плательщика. Возвращает запись и адрес страницы оплаты ЮKassa, куда отправляем человека."""
    house = check_can_pay(user, period)
    amount = price_for(db, period)
    if not amount:
        raise PaymentError("Для этого срока цена не задана")
    pay = Payment(user_id=user.id, household_id=house.id, email=user.email, period=period, amount=amount)
    db.add(pay)
    db.flush()
    body = {
        "amount": _amount(amount),
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": f"{_site()}/plus?paid={pay.id}"},
        "description": _description(user, period),
        "metadata": {"payment_id": str(pay.id), "user_id": str(user.id), "household_id": str(house.id), "period": period},
    }
    if auto_renew:
        body["save_payment_method"] = True
    data = _request("POST", "/payments", key=f"pay-{pay.id}", json=body)
    pay.yk_id = data["id"]
    if auto_renew:
        # Пока платёж не прошёл, автопродление не включаем; помним выбор в metadata ЮKassa и здесь:
        user.renew_period = period
    db.commit()
    return pay, data["confirmation"]["confirmation_url"]


def _until(house) -> datetime | None:
    """Конец Плюса семьи с часовым поясом (SQLite отдаёт время без него)."""
    if house is None or house.plus_until is None:
        return None
    return house.plus_until if house.plus_until.tzinfo else house.plus_until.replace(tzinfo=timezone.utc)


def extend_plus(house: Household, period: str, now: datetime | None = None) -> None:
    """Продлевает Плюс семьи: от конца текущего срока, если он ещё идёт, иначе от сегодняшнего дня.

    Здесь потолка в 13 месяцев нет: деньги уже получены, и срок выдаётся полностью. Потолок проверяется
    при создании платежа (check_can_pay).
    """
    house.plus_until = _new_end(house, period, now or datetime.now(timezone.utc))
    house.plan = PLUS
    house.plus_is_trial = False


def end_plus(db: Session, house: Household, pay: Payment, now: datetime) -> None:
    """Возврат денег или чарджбэк: Плюс семьи заканчивается сразу (R15), автопродление выключается (R21).

    Любой возврат закрывает весь Плюс, даже если оплачено вперёд несколько периодов: иначе можно было бы
    вернуть деньги и сохранить срок. Бессрочный Плюс, выданный администратором, возврат не трогает.
    """
    until = _until(house)
    if house.plan == PLUS and until is not None and until > now:
        house.plus_until = now
    for person in {pay.user_id, getattr(owner_of(house), "id", None)} - {None}:
        who = db.get(User, person)
        if who is not None:
            stop_autorenew(who)


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
    # Плюс получает семья, за которую платили (R06), а не та, где плательщик оказался к моменту уведомления.
    # Платежи без семьи (созданы прежней версией кода) идут семье плательщика.
    house = db.get(Household, pay.household_id) if pay.household_id else (user.household if user else None)
    if status == "succeeded" and pay.status == "pending":
        if paid_rub is not None and int(float(paid_rub)) != pay.amount:
            log.error("Платёж %s: сумма %s не совпадает с %s, Плюс не выдан", yk_id, paid_rub, pay.amount)
        else:
            pay.status = "succeeded"
            pay.paid_at = datetime.now(timezone.utc)
            if house is None:
                log.error("Платёж %s оплачен, но семьи, которой он предназначался, уже нет: Плюс никому не выдан", yk_id)
            else:
                extend_plus(house, pay.period, pay.paid_at)
                compression.restore(db, house)  # Плюс снова идёт: аптечки оживают, окно выбора состава закрыто (R14)
            if user and house is not None:
                method = data.get("payment_method") or {}
                owner = owner_of(house)
                if method.get("saved") and method.get("id") and not pay.recurring and owner is user:
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
        if house is not None:
            end_plus(db, house, pay, datetime.now(timezone.utc))
        elif user:
            stop_autorenew(user)
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
    users = db.scalars(select(User).where(User.auto_renew.is_(True), User.pay_method_id.is_not(None)))
    for user in list(users):
        house = user.household
        if owner_of(house) is not user:
            # Карта осталась у человека, который не владелец семьи (данные до правила «платит владелец», R06): не списываем.
            log.warning("Автопродление пользователя %s отключено: он не владелец семьи", user.id)
            stop_autorenew(user)
            db.commit()
            continue
        until = _until(house)
        if until is None:
            continue
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
    pay = Payment(user_id=user.id, household_id=user.household_id, email=user.email, period=period, amount=price, recurring=True, yk_id=None)
    db.add(pay)
    db.flush()
    try:
        data = _request("POST", "/payments", key=key, json={
            "amount": _amount(price), "capture": True, "payment_method_id": user.pay_method_id,
            "description": _description(user, period),
            "metadata": {"payment_id": str(pay.id), "user_id": str(user.id), "household_id": str(user.household_id), "period": period},
        })
        pay.yk_id = data["id"]
        db.commit()
        sync_payment(db, data["id"])
    except PaymentError:
        pay.status = "canceled"
        pay.yk_id = key  # чтобы не повторять попытку каждую минуту
        _renewal_failed(user)
        db.commit()
