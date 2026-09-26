from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_family
from ..models import Category, Family, Medicine
from ..schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/api/families/{family_id}/categories", tags=["categories"])


def _get(db: Session, fam: Family, cid: int) -> Category:
    c = db.get(Category, cid)
    if not c or c.family_id != fam.id:
        raise HTTPException(404, "Категория не найдена")
    return c


@router.get("", response_model=list[CategoryOut])
def list_categories(fam: Family = Depends(get_family), db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(Medicine.category_id, func.count()).where(Medicine.family_id == fam.id).group_by(Medicine.category_id)
        ).all()
    )
    cats = db.scalars(select(Category).where(Category.family_id == fam.id).order_by(Category.sort, Category.name))
    return [CategoryOut.model_validate(c).model_copy(update={"medicine_count": counts.get(c.id, 0)}) for c in cats]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, fam: Family = Depends(get_family), db: Session = Depends(get_db)):
    sort = (db.scalar(select(func.max(Category.sort)).where(Category.family_id == fam.id)) or 0) + 1
    c = Category(family_id=fam.id, sort=sort, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, fam: Family = Depends(get_family), db: Session = Depends(get_db)):
    c = _get(db, fam, category_id)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, fam: Family = Depends(get_family), db: Session = Depends(get_db)):
    db.delete(_get(db, fam, category_id))  # у лекарств категория станет пустой
    db.commit()
    return Response(status_code=204)
