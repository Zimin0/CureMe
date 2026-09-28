from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import current_user, get_family
from ..models import Family, Intake, User
from ..schemas import IntakeOut, IntakeUpdate
from ..services import intake_out, member_names

router = APIRouter(prefix="/api/families/{family_id}/intakes", tags=["intakes"])


@router.get("", response_model=list[IntakeOut])
def list_intakes(
    medicine_id: int | None = None,
    mine: bool = False,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """История приёма всей семьи, новые сверху. before — для подгрузки следующей страницы."""
    q = (
        select(Intake).where(Intake.family_id == fam.id).options(selectinload(Intake.user))
        .order_by(Intake.taken_at.desc(), Intake.id.desc()).limit(limit)
    )
    if medicine_id is not None:
        q = q.where(Intake.medicine_id == medicine_id)
    if mine:
        q = q.where(Intake.user_id == user.id)
    if before is not None:
        q = q.where(Intake.taken_at < before)
    names = member_names(db, fam.id)
    return [intake_out(i, user.id, names) for i in db.scalars(q)]


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
