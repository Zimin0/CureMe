"""Фото лекарств и выгрузка списка в txt."""

import secrets
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user, get_family
from ..models import Family, Medicine, User
from ..schemas import MedicineDetail
from ..services import load_medicines, medicine_out, member_names, stock_of

router = APIRouter(prefix="/api", tags=["files"])

# Проверяем «магические байты», а не расширение: расширение легко подделать.
SIGNATURES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png", b"RIFF": ".webp"}


def media_dir() -> Path:
    d = get_settings().media_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drop_photo(name: str | None) -> None:
    if name:
        (media_dir() / name).unlink(missing_ok=True)


@router.put("/families/{family_id}/medicines/{medicine_id}/photo", response_model=MedicineDetail)
async def upload_photo(
    medicine_id: int, file: UploadFile = File(...),
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    med = db.get(Medicine, medicine_id)
    if not med or med.family_id != fam.id:
        raise HTTPException(404, "Лекарство не найдено")
    limit = get_settings().max_photo_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Фото больше {get_settings().max_photo_mb} МБ")
    ext = next((e for sig, e in SIGNATURES.items() if data.startswith(sig)), None)
    if not ext or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise HTTPException(415, "Нужна картинка JPG, PNG или WebP")
    # Случайное имя: по нему фото и отдаётся, угадать его нельзя.
    name = secrets.token_urlsafe(16) + ext
    (media_dir() / name).write_bytes(data)
    _drop_photo(med.photo)
    med.photo = name
    db.commit()
    return medicine_out(load_medicines(db, fam.id, [med.id])[0], user.id, member_names(db, fam.id), detail=True)


@router.delete("/families/{family_id}/medicines/{medicine_id}/photo", response_model=MedicineDetail)
def delete_photo(
    medicine_id: int, fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    med = db.get(Medicine, medicine_id)
    if not med or med.family_id != fam.id:
        raise HTTPException(404, "Лекарство не найдено")
    _drop_photo(med.photo)
    med.photo = None
    db.commit()
    return medicine_out(load_medicines(db, fam.id, [med.id])[0], user.id, member_names(db, fam.id), detail=True)


@router.get("/media/{name}", include_in_schema=False)
def media(name: str):
    path = (media_dir() / name).resolve()
    if path.parent != media_dir().resolve() or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/families/{family_id}/export.txt", response_class=PlainTextResponse)
def export_txt(
    in_stock: bool = Query(default=False, description="Только то, что есть в наличии"),
    fam: Family = Depends(get_family), db: Session = Depends(get_db),
):
    """Список лекарств: только название и дозировка, по одному на строку."""
    lines = []
    for med in load_medicines(db, fam.id):
        if in_stock and stock_of(med).total <= 0:
            continue
        lines.append(f"{med.name} — {med.dosage}" if med.dosage else med.name)
    filename = f"Лекарства {fam.name} {date.today():%d.%m.%Y}.txt"
    return PlainTextResponse(
        "\n".join(lines) + ("\n" if lines else ""),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"kapsulka-lekarstva-{date.today():%Y-%m-%d}.txt\"; filename*=UTF-8''{quote(filename)}"},
    )
