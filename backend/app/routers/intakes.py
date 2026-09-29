from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import current_user, get_family
from ..models import Family, Intake, User
from ..schemas import IntakeOut, IntakeUpdate
from ..services import intake_out, member_names

router = APIRouter(prefix="/api/families/{family_id}/intakes", tags=["intakes"])


def _folded(col):
    """Текст для поиска без учёта регистра и разницы «ё/е»."""
    return func.replace(func.lower(col), "ё", "е")


@router.get("", response_model=list[IntakeOut])
def list_intakes(
    medicine_id: int | None = None,
    mine: bool = False,
    user_id: int | None = None,
    q: str = Query(default="", max_length=100),
    since: datetime | None = None,
    until: datetime | None = None,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """История приёма всей семьи, новые сверху.

    Фильтры: лекарство, кто принимал (mine или user_id), текст q (название лекарства или свой
    комментарий), период [since, until). before — для подгрузки следующей страницы.
    """
    query = (
        select(Intake).where(Intake.family_id == fam.id).options(selectinload(Intake.user))
        .order_by(Intake.taken_at.desc(), Intake.id.desc()).limit(limit)
    )
    if medicine_id is not None:
        query = query.where(Intake.medicine_id == medicine_id)
    if mine:
        query = query.where(Intake.user_id == user.id)
    if user_id is not None:
        query = query.where(Intake.user_id == user_id)
    if text := q.strip().lower().replace("ё", "е"):
        like = _folded(Intake.medicine_name).contains(text, autoescape=True)
        # Чужие комментарии скрыты, поэтому и искать по ним нельзя: иначе поиск выдаст их содержание.
        own_comment = and_(Intake.user_id == user.id, _folded(Intake.comment).contains(text, autoescape=True))
        query = query.where(or_(like, own_comment))
    if since is not None:
        query = query.where(Intake.taken_at >= since)
    if until is not None:
        query = query.where(Intake.taken_at < until)
    if before is not None:
        query = query.where(Intake.taken_at < before)
    names = member_names(db, fam.id)
    return [intake_out(i, user.id, names) for i in db.scalars(query)]


@router.patch("/{intake_id}", response_model=IntakeOut)
def update_intake(
    intake_id: int, body: IntakeUpdate,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Комментарий можно дописать и позже, но только к своей записи."""
    i = db.get(Intake, intake_id)
    if not i or i.family_id != fam.id:
        raise HTTPException(404, "Запись не найдена")
    if i.user_id != user.id:
        raise HTTPException(403, "Комментарий может менять только тот, кто принимал лекарство")
    i.comment = body.comment.strip()
    db.commit()
    return intake_out(i, user.id, member_names(db, fam.id))
