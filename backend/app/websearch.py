"""Поиск лекарства по штрихкоду через обычный веб-поиск.

Специальной бесплатной базы российских штрихкодов лекарств нет, зато почти
любая аптека пишет штрихкод на странице товара. Поэтому ищем код в поисковике
и собираем ответ из заголовков найденных страниц:
«Ларингобакт таблетки для рассасывания 20мг+10мг №30 | Аптека …».
Разные аптеки называют товар чуть по-разному, поэтому название выбираем
«голосованием» — то, что встречается в большинстве заголовков.
"""

import html
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import httpx

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

# Лекарственная форма → (как показывать, единица учёта).
FORMS: list[tuple[str, str, str]] = [
    (r"таблетк\w*|табл\.?|таб\.", "Таблетки", "таб"),
    (r"капсул\w*|капс\.?", "Капсулы", "капс"),
    (r"пастилк\w*|леденц\w*", "Пастилки", "шт"),
    (r"драже", "Драже", "шт"),
    (r"сироп\w*", "Сироп", "мл"),
    (r"суспензи\w*", "Суспензия", "мл"),
    (r"капл\w*", "Капли", "мл"),
    (r"спре\w*|аэрозол\w*", "Спрей", "мл"),
    (r"раствор\w*|р-р", "Раствор", "мл"),
    (r"мазь|мази", "Мазь", "г"),
    (r"гел[ья]\w*", "Гель", "г"),
    (r"крем\w*", "Крем", "г"),
    (r"порош\w*|пакетик\w*|саше", "Порошок", "пак"),
    (r"гранул\w*", "Гранулы", "пак"),
    (r"суппозитор\w*|свеч\w*", "Свечи", "шт"),
    (r"ампул\w*|амп\.", "Ампулы", "амп"),
    (r"пластыр\w*", "Пластырь", "шт"),
]
FORM_RE = re.compile(r"\b(" + "|".join(p for p, _, _ in FORMS) + r")", re.I)
NUM = r"\d+(?:[.,]\d+)?"
UNIT = r"(?:мг|мкг|г|мл|ме|%|mg)"
DOSAGE_RE = re.compile(rf"{NUM}\s*{UNIT}(?:\s*\+\s*{NUM}\s*{UNIT}?)*(?:\s*/\s*{NUM}?\s*(?:мл|доз\w*))?", re.I)
COUNT_RES = [
    re.compile(r"№\s*(\d{1,4})"),
    re.compile(r"\bN\s?(\d{1,4})\b"),
    re.compile(r"\b(\d{1,4})\s*(?:шт|таб\w*|капс\w*|пак\w*|пастил\w*|свеч\w*|амп\w*|суппоз\w*)\b", re.I),
]
# Всё, что аптеки дописывают к названию товара.
TAIL_RE = re.compile(
    r"\s*(?:\||—|–| - |::|купить|цена|инструкци|отзыв|в наличии|заказать|доставк|аналог|в москве|в спб|в санкт).*$",
    re.I,
)


@dataclass
class WebProduct:
    name: str                     # «Ларингобакт»
    title: str                    # «Ларингобакт таблетки для рассасывания 20 мг + 10 мг №30»
    form: str | None = None
    dosage: str | None = None
    pack_size: float | None = None
    unit: str | None = None
    sources: list[str] = field(default_factory=list)


def clean_title(title: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", "", title)).replace("\xa0", " ")
    t = TAIL_RE.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" ,.;:-")


def _norm_dosage(d: str) -> str:
    d = re.sub(r"\s+", "", d.lower()).replace("mg", "мг").replace(",", ".")
    d = re.sub(rf"({NUM})({UNIT})", r"\1 \2", d)
    return d.replace("+", " + ").replace("/", " / ")


def parse_title(title: str) -> dict | None:
    """Разбирает один заголовок. None — если это не похоже на карточку лекарства."""
    t = clean_title(title)
    m = FORM_RE.search(t)
    if not m or m.start() == 0:
        return None
    name = t[: m.start()].strip(" ,-«»\"")
    # Название — это 1–3 слова до формы, без цифр и мусора вроде «Купить».
    if not name or len(name) > 60 or re.search(r"\d{5,}|купить|цена", name, re.I):
        return None
    form_word = m.group(1).lower()
    form, unit = next(((f, u) for p, f, u in FORMS if re.fullmatch(p, form_word, re.I)), (None, None))
    # «таблетки для рассасывания», «капли назальные» — берём уточнение до цифр.
    rest = t[m.end():]
    extra = re.match(r"\s*((?:для\s+\w+|покрыт\w+(?:\s+\w+)?|шипуч\w+|назальн\w+|глазн\w+|жеват\w+|диспергир\w+|п/о|кишечнораств\w+)(?:\s+[а-яё]+)?)", rest, re.I)
    if form and extra:
        form = f"{form} {extra.group(1).strip().lower()}"
    dosage = DOSAGE_RE.search(rest)
    count = None
    for r in COUNT_RES:
        if c := r.search(rest):
            count = float(c.group(1))
            break
    if count is None and unit in ("мл", "г"):
        # Флакон или тюбик: объём в конце заголовка, не путая с дозировкой «0,01%».
        vols = re.findall(rf"({NUM})\s*{unit}\b", rest.replace(dosage.group(0), "") if dosage else rest)
        if vols:
            count = float(vols[-1].replace(",", "."))
    return {
        "name": name[:1].upper() + name[1:],
        "form": form,
        "unit": unit,
        "dosage": _norm_dosage(dosage.group(0)) if dosage else None,
        "pack_size": count,
    }


def _vote(values: list) -> object | None:
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else None


def combine(titles: list[str], urls: list[str] | None = None) -> WebProduct | None:
    """Собирает ответ из нескольких заголовков голосованием по каждому полю."""
    parsed = [(p, (urls or [None] * len(titles))[i]) for i, t in enumerate(titles) if (p := parse_title(t))]
    if not parsed:
        return None
    name_key = _vote([p["name"].lower() for p, _ in parsed])
    same = [(p, u) for p, u in parsed if p["name"].lower() == name_key]
    # Среди вариантов написания имени берём самый частый (регистр как у большинства).
    name = _vote([p["name"] for p, _ in same])
    form = _vote([p["form"] for p, _ in same])
    dosage = _vote([p["dosage"] for p, _ in same])
    pack = _vote([p["pack_size"] for p, _ in same])
    unit = _vote([p["unit"] for p, _ in same])
    title = " ".join(x for x in [name, (form or "").lower(), dosage, f"№{int(pack)}" if pack else None] if x)
    return WebProduct(
        name=name, title=title, form=form, dosage=dosage, pack_size=pack, unit=unit,
        sources=[u for _, u in same if u][:5],
    )


# --- поисковики ---------------------------------------------------------------

def _duckduckgo(client: httpx.Client, q: str) -> list[tuple[str, str]]:
    r = client.post("https://html.duckduckgo.com/html/", data={"q": q, "kl": "ru-ru"})
    r.raise_for_status()
    return [(t, u) for u, t in re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)]


def _bing(client: httpx.Client, q: str) -> list[tuple[str, str]]:
    r = client.get(f"https://www.bing.com/search?q={quote_plus(q)}&setlang=ru&cc=RU")
    r.raise_for_status()
    return [(t, u) for u, t in re.findall(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)]


ENGINES = [("duckduckgo", _duckduckgo), ("bing", _bing)]


def search_barcode(code: str, timeout: float = 6.0) -> WebProduct | None:
    """Ищет EAN в интернете. Любая сетевая ошибка — просто None, сканирование от этого не ломается."""
    with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
        for engine, fn in ENGINES:
            try:
                hits = fn(client, code)
            except (httpx.HTTPError, ValueError) as e:
                log.info("web search %s failed for %s: %s", engine, code, e)
                continue
            product = combine([t for t, _ in hits], [u for _, u in hits])
            if product:
                log.info("web search %s: %s -> %s", engine, code, product.title)
                return product
    return None


if __name__ == "__main__":  # python -m app.websearch 4605077018932
    import sys

    logging.basicConfig(level=logging.INFO)
    print(search_barcode(sys.argv[1]))
