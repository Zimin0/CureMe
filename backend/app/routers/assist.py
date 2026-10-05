"""Главная, подбор по болезни и сканирование."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..codes import display_code, parse_code
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, get_family
from ..lookup import cached_product, find_product
from ..models import Family, Membership, User
from ..ratelimit import limiter
from ..schemas import OverviewOut, ProductInfo, ScanIn, ScanOut, SuggestionOut, SuggestOut
from ..search import best_match, expand_query
from ..seed import COMMON_CONDITIONS
from ..plans import require_plus
from ..services import (
    find_package_by_serial, indication_hints, load_household_medicines, load_medicines, medicine_out, member_names,
)

router = APIRouter(prefix="/api", tags=["assist"])

DISCLAIMER = (
    "Подсказка строится по тому, что вы сами записали в аптечку. Это не медицинский совет: "
    "сверяйтесь с инструкцией, а при сильных или непонятных симптомах обращайтесь к врачу."
)


@router.get("/conditions", response_model=list[str])
def conditions():
    return COMMON_CONDITIONS


@router.get("/indication-hints", response_model=list[str])
def get_indication_hints(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """Быстрые подсказки к полю «От чего помогает»; список задаёт администратор."""
    return indication_hints(db)


@router.get("/families/{family_id}/overview", response_model=OverviewOut)
def overview(fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db)):
    names = member_names(db, fam.id)
    meds = load_medicines(db, fam.id)
    items = [medicine_out(m, user.id, names) for m in meds]

    def by_expiry(m):
        return m.stock.days_left if m.stock.days_left is not None else 10**6

    return OverviewOut(
        total_medicines=len(items),
        total_packages=sum(m.stock.package_count for m in items),
        expired=[m for m in items if m.stock.status == "expired"],
        expiring=sorted([m for m in items if m.stock.status == "expiring"], key=by_expiry),
        low=[m for m in items if m.stock.status in ("low", "out")],
        favorites=[m for m in items if m.is_favorite],
        helps_me=[m for m in items if m.helps_me],
        expiring_soon_days=get_settings().expiring_soon_days,
    )


@router.get("/families/{family_id}/suggest", response_model=SuggestOut)
def suggest(
    condition: str = Query(min_length=2, max_length=100),
    scope: str | None = Query(default=None, pattern="^all$", description="all — по всем аптечкам семьи (Плюс)"),
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    phrases = expand_query(condition)
    if scope == "all":
        require_plus(db, fam, "search_all")
        pairs = load_household_medicines(db, fam)
    else:
        pairs = [(fam, m) for m in load_medicines(db, fam.id)]
    names_by_cabinet: dict[int, dict[int, str]] = {}
    results: list[SuggestionOut] = []
    for cab, med in pairs:
        out = medicine_out(med, user.id, names_by_cabinet.setdefault(cab.id, member_names(db, cab.id)))
        if scope == "all":
            out.family_id, out.family_name = cab.id, cab.name
        s_ind, w_ind = best_match(phrases, med.indications)
        # каждую категорию сравниваем отдельно, чтобы фраза не «склеилась» из двух соседних
        s_cat, w_cat, cat_hit = max(
            ((*best_match(phrases, c.name), c.name) for c in med.categories), default=(0.0, None, None),
            key=lambda x: x[0],
        )
        s_name, _ = best_match(phrases, " ".join(filter(None, [med.name, med.active_ingredient, med.notes])))
        base = s_ind * 10 + s_cat * 5 + s_name * 3
        if base <= 0:
            continue
        reasons, warnings = [], []
        if w_ind:
            reasons.append(f"В показаниях: «{w_ind}»")
        if w_cat:
            reasons.append(f"Категория «{cat_hit}»")
        if not reasons:
            reasons.append("Совпадает название или заметка")
        score = base
        if out.helps_me:
            score += 6
            reasons.insert(0, "Вам помогает")
        if out.is_favorite:
            score += 2
        if out.helps_members:
            score += 1
            reasons.append("Помогает: " + ", ".join(out.helps_members))
        st = out.stock
        if st.total <= 0:
            score -= 8
            warnings.append("Закончилось" if st.expired_quantity == 0 else "Осталось только просроченное")
        else:
            score += 2
            if st.status == "expired":
                warnings.append("Есть просроченная упаковка — берите годную")
            if st.days_left is not None and st.days_left <= get_settings().expiring_soon_days:
                warnings.append(f"Срок истекает через {st.days_left} дн.")
        if med.contraindications:
            warnings.append(f"Противопоказания: {med.contraindications}")
        results.append(SuggestionOut(medicine=out, score=round(score, 2), reasons=reasons, warnings=warnings))
    results.sort(key=lambda r: -r.score)
    return SuggestOut(query=condition, results=results, disclaimer=DISCLAIMER)


@router.post("/families/{family_id}/scan", response_model=ScanOut)
def scan(body: ScanIn, fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Незнакомый код ищется в интернете: не даём превратить сервер в робота, долбящего поисковики.
    limiter.hit(f"lookup:{user.id}", limit=60, window=60)
    parsed = parse_code(body.raw)
    if not parsed.gtin:
        raise HTTPException(422, "Не получилось распознать код товара. Попробуйте штрихкод или DataMatrix.")

    med_row = next(
        (m for m in load_medicines(db, fam.id) if m.gtin == parsed.gtin), None
    )
    medicine = medicine_out(med_row, user.id, member_names(db, fam.id)) if med_row else None
    duplicate = bool(parsed.serial and find_package_by_serial(db, fam.id, parsed.gtin, parsed.serial))

    # Для уже известного лекарства в сеть не ходим — хватит справочника (там размер блистера).
    row = cached_product(db, parsed.gtin, fam.id) if medicine else find_product(db, parsed.gtin, family_id=fam.id)
    db.commit()
    product = ProductInfo.model_validate(row) if row else None

    return ScanOut(
        parsed=parsed.to_dict(), display_code=display_code(parsed.gtin),
        medicine=medicine, product=product, duplicate_package=duplicate,
    )


@router.get("/products/{code}", response_model=ProductInfo)
def product(
    code: str, refresh: bool = False, family_id: int | None = None,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Поиск товара по штрихкоду (кнопка «Найти по коду» в форме). С family_id сначала смотрит записи этой аптечки."""
    limiter.hit(f"lookup:{user.id}", limit=60, window=60)
    if family_id is not None and not db.scalar(
        select(Membership.id).where(Membership.family_id == family_id, Membership.user_id == user.id)
    ):
        raise HTTPException(404, "Семья не найдена")
    parsed = parse_code(code)
    if not parsed.gtin:
        raise HTTPException(422, "Это не похоже на штрихкод")
    row = find_product(db, parsed.gtin, refresh=refresh, family_id=family_id)
    db.commit()
    if not row:
        raise HTTPException(404, "В интернете ничего не нашлось по этому коду. Впишите название вручную.")
    return ProductInfo.model_validate(row)
