"""Выписка «для врача» в PDF и Excel: история приёма одного участника семьи за период.

Функция Капсулки Плюс; простой текстовый список лекарств (files.py, export.txt) остаётся бесплатным.
"""

from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..doctor_report import collect, render_pdf, render_xlsx
from ..models import Family, Membership, User
from ..plans import plus_feature

router = APIRouter(prefix="/api/families/{family_id}/report", tags=["reports"])

MAX_DAYS = 366 * 3
FORMATS = {
    "pdf": (render_pdf, "application/pdf"),
    "xlsx": (render_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


@router.get(".{fmt}", response_class=Response, responses={200: {"content": {m: {} for _, m in FORMATS.values()}}})
def doctor_report(
    fmt: str,
    member: int | None = Query(default=None, description="Чья история; по умолчанию своя"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    tz: str = Query(default="Europe/Moscow", max_length=64, description="Часовой пояс браузера"),
    fam: Family = Depends(plus_feature("export_pdf")), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if fmt not in FORMATS:
        raise HTTPException(404, "Такого формата нет")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Неизвестный часовой пояс")
    date_to = date_to or datetime.now(zone).date()  # «сегодня» у пользователя, а не на сервере
    date_from = date_from or date_to - timedelta(days=29)
    if date_from > date_to:
        raise HTTPException(422, "Начало периода позже конца")
    if (date_to - date_from).days > MAX_DAYS:
        raise HTTPException(422, "Период не больше трёх лет")
    patient = user
    if member is not None and member != user.id:
        m = db.scalar(select(Membership).where(Membership.family_id == fam.id, Membership.user_id == member))
        if not m:
            raise HTTPException(404, "Участник не найден")
        patient = m.user

    report = collect(db, fam, user, patient, date_from, date_to, zone)
    render, media = FORMATS[fmt]
    ascii_name, name = report.filename(fmt)
    return Response(
        render(report), media_type=media,
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"},
    )
