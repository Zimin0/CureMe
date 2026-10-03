"""Фото лекарств и выгрузка списка в txt."""

import csv
import io
import json
import secrets
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user, get_family
from ..deps import family_membership
from ..models import Family, Intake, Medicine, Membership, User
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


def _attachment(name: str, ascii_name: str) -> dict[str, str]:
    return {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"}


@router.get("/families/{family_id}/export.{fmt}", response_class=Response)
def export_data(fmt: str, m: Membership = Depends(family_membership), db: Session = Depends(get_db)):
    """Выгрузка данных аптечки в CSV или JSON (R25): бесплатно и в замороженной аптечке тоже; свои приёмы только в JSON."""
    if fmt not in ("csv", "json"):
        raise HTTPException(404, "Такого формата нет")
    fam = m.family
    meds = load_medicines(db, fam.id)
    today = date.today()
    if fmt == "json":
        intakes = db.scalars(select(Intake).where(Intake.family_id == fam.id, Intake.user_id == m.user_id).order_by(Intake.taken_at))
        data = {
            "cabinet": fam.name, "exported_at": today.isoformat(),
            "medicines": [{
                "name": x.name, "form": x.form, "dosage": x.dosage, "active_ingredient": x.active_ingredient,
                "manufacturer": x.manufacturer, "indications": x.indications, "contraindications": x.contraindications,
                "notes": x.notes, "unit": x.unit, "gtin": x.gtin, "min_quantity": x.min_quantity,
                "categories": [c.name for c in x.categories],
                "packages": [{"quantity": p.quantity, "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
                              "opened_at": p.opened_at.isoformat() if p.opened_at else None, "batch": p.batch, "location": p.location}
                             for p in x.packages],
            } for x in meds],
            "my_intakes": [{"medicine": i.medicine_name, "amount": i.amount, "unit": i.unit, "taken_at": i.taken_at.isoformat(),
                            "comment": i.comment} for i in intakes],
        }
        body, media, ext = json.dumps(data, ensure_ascii=False, indent=2), "application/json; charset=utf-8", "json"
    else:
        buf = io.StringIO()
        out = csv.writer(buf)
        out.writerow(["Лекарство", "Форма", "Дозировка", "Действующее вещество", "Производитель", "От чего помогает", "Противопоказания",
                      "Заметки", "Единица", "Штрихкод", "Категории", "Количество в упаковке", "Срок годности", "Вскрыта", "Партия", "Место"])
        for x in meds:
            head = [x.name, x.form or "", x.dosage or "", x.active_ingredient or "", x.manufacturer or "", x.indications,
                    x.contraindications, x.notes, x.unit, x.gtin or "", "; ".join(c.name for c in x.categories)]
            for p in x.packages or [None]:
                tail = ["", "", "", "", ""] if p is None else [p.quantity, p.expiry_date or "", p.opened_at or "", p.batch or "", p.location or ""]
                out.writerow(head + tail)
        body, media, ext = "\ufeff" + buf.getvalue(), "text/csv; charset=utf-8", "csv"  # BOM: Excel открывает кириллицу правильно
    name = f"Аптечка {fam.name} {today:%d.%m.%Y}.{ext}"
    return Response(body, media_type=media, headers=_attachment(name, f"kapsulka-aptechka-{today:%Y-%m-%d}.{ext}"))
