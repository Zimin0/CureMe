from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_family
from ..models import Category, Family, Medicine, MedicineCategory
from ..schemas import CategoryOut

# Категории общие для всех; список, созданный или изменённый администратором, видят все семьи.
# Счётчик лекарств здесь — только по своей семье. Изменение категорий — в routers/admin.py.
router = APIRouter(prefix="/api/families/{family_id}/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(fam: Family = Depends(get_family), db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(MedicineCategory.category_id, func.count())
            .join(Medicine)
            .where(Medicine.family_id == fam.id)
            .group_by(MedicineCategory.category_id)
        ).all()
    )
    cats = db.scalars(select(Category).order_by(Category.sort, Category.name))
    return [CategoryOut.model_validate(c).model_copy(update={"medicine_count": counts.get(c.id, 0)}) for c in cats]
