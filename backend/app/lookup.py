"""Поиск товара по коду: общий справочник → поиск в интернете → Open Food Facts.

Всё найденное в интернете сразу сохраняется в общий справочник product_codes, так что
повторное сканирование того же товара (в любой семье) не ходит в сеть. Правки людей лежат отдельно, в
family_products, и видны только их аптечке: общий справочник нельзя испортить из своего аккаунта.
"""

import logging

import httpx
from sqlalchemy.orm import Session

from .config import get_settings
from .models import FamilyProduct, ProductCode
from .websearch import search_barcode

log = logging.getLogger(__name__)
PRODUCT_FIELDS = ("name", "form", "dosage", "active_ingredient", "manufacturer", "title", "unit", "pack_size", "blister_size")


def guess_blister_size(pack_size: float | None, unit: str | None) -> int | None:
    """В большинстве пачек блистеры по 10 штук; для 6/8/12/14/20 — чаще весь счёт кратен им."""
    if not pack_size or unit not in ("таб", "капс", "шт"):
        return None
    n = int(pack_size)
    for size in (10, 12, 14, 8, 6, 7, 5, 4):
        if n % size == 0 and n >= size:
            return size
    return n


def remember_product(
    db: Session, gtin: str, source: str = "user", family_id: int | None = None, **fields
) -> ProductCode | FamilyProduct | None:
    """Сохраняет только «товарные» поля — ничего личного из аптечки семьи.

    Правка человека (source="user") идёт в справочник его аптечки. В общий справочник попадает только то,
    что нашлось в интернете: оттуда его видят все, и подменить запись из аккаунта нельзя."""
    if not fields.get("name"):
        return None
    if source == "user":
        if family_id is None:
            return None
        row = db.get(FamilyProduct, (family_id, gtin)) or FamilyProduct(family_id=family_id, gtin=gtin)
    else:
        row = db.get(ProductCode, gtin) or ProductCode(gtin=gtin)
        row.source = source
    for k in PRODUCT_FIELDS:
        if fields.get(k):
            setattr(row, k, fields[k])
    db.add(row)
    return row


def cached_product(db: Session, gtin: str, family_id: int | None = None) -> ProductCode | FamilyProduct | None:
    """Своя запись аптечки, иначе общий справочник. Старые записи людей в общем справочнике (source=user,
    появились до разделения) не показываем: определить, кто их вписал, нельзя."""
    if family_id is not None and (own := db.get(FamilyProduct, (family_id, gtin))):
        return own
    row = db.get(ProductCode, gtin)
    return row if row and row.source != "user" else None


def lookup_openfoodfacts(gtin: str) -> dict | None:
    """В Open Food Facts есть и часть аптечных товаров; покрытие лекарств небольшое."""
    ean = gtin[1:] if gtin.startswith("0") else gtin
    try:
        r = httpx.get(
            f"https://world.openfoodfacts.org/api/v2/product/{ean}.json",
            params={"fields": "product_name,product_name_ru,brands"},
            headers={"User-Agent": "CureMe/1.0 (home medicine cabinet)"},
            timeout=4,
        )
        data = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError) as e:
        log.info("openfoodfacts failed for %s: %s", gtin, e)
        return None
    p = data.get("product") if data.get("status") == 1 else None
    name = p and (p.get("product_name_ru") or p.get("product_name"))
    return {"name": name, "manufacturer": p.get("brands") or None} if name else None


def find_product(
    db: Session, gtin: str, refresh: bool = False, family_id: int | None = None
) -> ProductCode | FamilyProduct | None:
    """Справочник, а если там пусто (или просят обновить) — интернет с сохранением результата."""
    cached = cached_product(db, gtin, family_id)
    if cached and not refresh:
        return cached
    if not get_settings().remote_lookup:
        return cached
    ean = gtin[1:] if gtin.startswith("0") else gtin
    if web := search_barcode(ean):
        return remember_product(
            db, gtin, source="internet", name=web.name, title=web.title, form=web.form, dosage=web.dosage,
            unit=web.unit, pack_size=web.pack_size, blister_size=guess_blister_size(web.pack_size, web.unit),
        )
    if off := lookup_openfoodfacts(gtin):
        return remember_product(db, gtin, source="openfoodfacts", **off)
    return cached
