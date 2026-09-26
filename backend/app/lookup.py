"""Поиск названия товара по коду: сначала общий справочник, потом публичный источник."""

import logging

import httpx
from sqlalchemy.orm import Session

from .config import get_settings
from .models import ProductCode

log = logging.getLogger(__name__)


def product_from_cache(db: Session, gtin: str) -> ProductCode | None:
    return db.get(ProductCode, gtin)


def remember_product(db: Session, gtin: str, **fields) -> None:
    """Сохраняет только «товарные» поля — ничего личного из аптечки семьи."""
    if not fields.get("name"):
        return
    row = db.get(ProductCode, gtin) or ProductCode(gtin=gtin)
    for k in ("name", "form", "dosage", "active_ingredient", "manufacturer"):
        if fields.get(k):
            setattr(row, k, fields[k])
    row.source = "user"
    db.add(row)


def lookup_remote(gtin: str) -> dict | None:
    """Open Food Facts хранит и часть аптечных товаров. Покрытие лекарств небольшое,
    поэтому это лишь подсказка; при любой ошибке молча возвращаем None."""
    if not get_settings().remote_lookup:
        return None
    ean = gtin[1:] if gtin.startswith("0") else gtin
    try:
        r = httpx.get(
            f"https://world.openfoodfacts.org/api/v2/product/{ean}.json",
            params={"fields": "product_name,product_name_ru,brands,quantity"},
            headers={"User-Agent": "CureMe/1.0 (home medicine cabinet)"},
            timeout=4,
        )
        data = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError) as e:
        log.info("remote lookup failed for %s: %s", gtin, e)
        return None
    p = data.get("product") if data.get("status") == 1 else None
    name = p and (p.get("product_name_ru") or p.get("product_name"))
    if not name:
        return None
    return {"name": name, "manufacturer": p.get("brands") or None, "source": "openfoodfacts"}
