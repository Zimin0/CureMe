"""История болезней: личные записи человека с датами, комментарием и фото документов.

Записи привязаны к аккаунту, а не к семье: их видит и меняет только автор (это сведения о здоровье).
Фото лежат в media/illness под случайными именами и отдаются только автору по его токену.
"""

import secrets
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import IllnessDocument, IllnessRecord, User
from ..schemas import IllnessDocumentOut, IllnessIn, IllnessOut, IllnessUpdate
from .files import SIGNATURES, media_dir

router = APIRouter(prefix="/api/illnesses", tags=["illness"])

MAX_RECORDS = 500          # записей на человека
MAX_DOCUMENTS = 10         # фото на одну запись
MAX_SPAN_DAYS = 3660       # период одной записи
MIN_DATE = date(1900, 1, 1)


def _dir():
    d = media_dir() / "illness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drop_files(names: list[str]) -> None:
    for n in names:
        (_dir() / n).unlink(missing_ok=True)


def drop_user_files(db: Session, user: User) -> None:
    """Стирает с диска фото документов человека: вызывается перед удалением аккаунта (строки в базе уходят каскадом)."""
    names = db.scalars(
        select(IllnessDocument.filename).join(IllnessRecord).where(IllnessRecord.user_id == user.id)).all()
    _drop_files(list(names))


def _out(rec: IllnessRecord) -> IllnessOut:
    return IllnessOut(
        id=rec.id, title=rec.title, date_from=rec.date_from, date_to=rec.date_to, comment=rec.comment,
        documents=[IllnessDocumentOut(id=d.id, url=f"/api/illnesses/{rec.id}/documents/{d.id}") for d in rec.documents],
        created_at=rec.created_at, updated_at=rec.updated_at,
    )


def _check_period(start: date, end: date) -> None:
    if start < MIN_DATE or end < start:
        raise HTTPException(422, "Дата окончания не может быть раньше даты начала")
    if (end - start).days > MAX_SPAN_DAYS:
        raise HTTPException(422, "Период слишком длинный: разбейте его на несколько записей")


def _get(db: Session, user: User, record_id: int) -> IllnessRecord:
    rec = db.scalar(
        select(IllnessRecord).where(IllnessRecord.id == record_id, IllnessRecord.user_id == user.id)
        .options(selectinload(IllnessRecord.documents)))
    if not rec:
        raise HTTPException(404, "Запись не найдена")
    return rec


@router.get("", response_model=list[IllnessOut])
def list_records(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Свои записи, новые сверху."""
    q = (select(IllnessRecord).where(IllnessRecord.user_id == user.id)
         .options(selectinload(IllnessRecord.documents))
         .order_by(IllnessRecord.date_from.desc(), IllnessRecord.id.desc()))
    return [_out(r) for r in db.scalars(q)]


@router.post("", response_model=IllnessOut, status_code=201)
def create_record(body: IllnessIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    end = body.date_to or body.date_from
    _check_period(body.date_from, end)
    count = db.scalar(select(func.count()).select_from(IllnessRecord).where(IllnessRecord.user_id == user.id)) or 0
    if count >= MAX_RECORDS:
        raise HTTPException(409, f"Не больше {MAX_RECORDS} записей: удалите ненужные")
    rec = IllnessRecord(user_id=user.id, title=body.title, date_from=body.date_from, date_to=end, comment=body.comment)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _out(rec)


@router.patch("/{record_id}", response_model=IllnessOut)
def update_record(record_id: int, body: IllnessUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec = _get(db, user, record_id)
    data = body.model_dump(exclude_unset=True)
    start = data.get("date_from") or rec.date_from
    end = data.get("date_to") or rec.date_to
    if "date_to" not in data and rec.date_to == rec.date_from:
        end = start  # запись была одним днём: при смене даты она остаётся одним днём
    elif "date_to" not in data and end < start:
        end = start
    _check_period(start, end)
    rec.date_from, rec.date_to = start, end
    for key in ("title", "comment"):
        if data.get(key) is not None:
            setattr(rec, key, data[key])
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return _out(rec)


@router.delete("/{record_id}", status_code=204)
def delete_record(record_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec = _get(db, user, record_id)
    names = [d.filename for d in rec.documents]
    db.delete(rec)
    db.commit()
    _drop_files(names)
    return Response(status_code=204)


@router.post("/{record_id}/documents", response_model=IllnessOut, status_code=201)
async def add_document(
    record_id: int, file: UploadFile = File(...),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    rec = _get(db, user, record_id)
    if len(rec.documents) >= MAX_DOCUMENTS:
        raise HTTPException(409, f"Не больше {MAX_DOCUMENTS} фото в одной записи")
    limit = get_settings().max_photo_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Фото больше {get_settings().max_photo_mb} МБ")
    ext = next((e for sig, e in SIGNATURES.items() if data.startswith(sig)), None)
    if not ext or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise HTTPException(415, "Нужна картинка JPG, PNG или WebP")
    name = secrets.token_urlsafe(16) + ext
    (_dir() / name).write_bytes(data)
    rec.documents.append(IllnessDocument(filename=name))
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return _out(rec)


@router.get("/{record_id}/documents/{doc_id}", include_in_schema=False)
def get_document(record_id: int, doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec = _get(db, user, record_id)
    doc = next((d for d in rec.documents if d.id == doc_id), None)
    path = _dir() / doc.filename if doc else None
    if not doc or not path.is_file():
        raise HTTPException(404, "Фото не найдено")
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


@router.delete("/{record_id}/documents/{doc_id}", response_model=IllnessOut)
def delete_document(record_id: int, doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec = _get(db, user, record_id)
    doc = next((d for d in rec.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "Фото не найдено")
    name = doc.filename
    rec.documents.remove(doc)
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    _drop_files([name])
    return _out(rec)
