"""SEO: мета-теги публичных страниц, robots.txt и sitemap.xml.

Приложение — одностраничное (SPA): сервер отдаёт один index.html на все адреса. Поисковики
читают страницу хуже, чем браузер, поэтому для публичных адресов мы подставляем в index.html
свои title, description, canonical, Open Graph и короткий текст внутри #root. Закрытые разделы
получают noindex. Тексты без обещаний лечения: это учёт лекарств, а не медицинская услуга.
"""

import html
import json
import re

DEFAULT_BASE = "https://kapsulka.ru"
SITE = "Капсулка"

_FEATURES = [
    ("Добавление сканом", "Наведите камеру на код упаковки: название, срок годности и серия подставятся сами."),
    ("Сроки годности", "Видно, что скоро испортится, а что уже пора выбросить. Остатки считаются по таблеткам."),
    ("Вся семья в одной аптечке", "Родные видят общую аптечку со своих телефонов. У каждого свои избранные лекарства."),
    ("Что есть дома от…", "Введите, что беспокоит, и посмотрите, что из ваших лекарств указано в инструкции для такого случая."),
]

# Публичные страницы: путь -> (title, description, приоритет для sitemap)
PAGES = {
    "/": (
        "Капсулка — домашняя аптечка для всей семьи: сроки годности, остатки, сканер кода",
        "Капсулка — учёт домашней аптечки онлайн: сканируйте упаковки, следите за сроками годности и остатками, "
        "делитесь аптечкой с семьёй. Бесплатно, работает на телефоне.",
        "1.0",
    ),
    "/privacy": (
        "Политика конфиденциальности — Капсулка",
        "Как сервис «Капсулка» собирает, хранит и защищает персональные данные пользователей.",
        "0.3",
    ),
    "/terms": (
        "Пользовательское соглашение — Капсулка",
        "Условия использования сервиса «Капсулка»: права и обязанности пользователей и владельца сайта.",
        "0.3",
    ),
    "/consent": (
        "Согласие на обработку персональных данных — Капсулка",
        "Текст согласия на обработку персональных данных при регистрации в сервисе «Капсулка».",
        "0.3",
    ),
}

DISALLOW = [
    "/api/", "/admin", "/login", "/register", "/join/", "/verify-email", "/trusted",
    "/medicines", "/scan", "/find", "/schedule", "/history", "/family", "/plus", "/export",
    "/consent-telegram", "/consent-trusted", "/consent-share",
]


def normalize(path: str) -> str:
    path = "/" + path.strip("/")
    return path


def base_url(public_url: str, request_base: str) -> str:
    return (public_url or request_base or DEFAULT_BASE).rstrip("/")


def _json_ld(base: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": SITE,
        "url": base + "/",
        "inLanguage": "ru",
        "applicationCategory": "HealthApplication",
        "operatingSystem": "Web, Android, iOS",
        "description": PAGES["/"][1],
        "image": base + "/icon-512.png",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB", "description": "Бесплатный тариф"},
    }
    # "</" в JSON внутри <script> закрыл бы тег раньше времени
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _prerender_home() -> str:
    items = "".join(f"<li><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></li>" for t, d in _FEATURES)
    return (
        "<main><h1>Домашняя аптечка, в которой всё под контролем</h1>"
        "<p>Капсулка помнит, какие лекарства есть у вас дома, когда истекает срок и сколько осталось. "
        "Вся семья смотрит в одну аптечку с телефона.</p>"
        f"<h2>Что умеет Капсулка</h2><ul>{items}</ul>"
        "<p>Капсулка помогает вести учёт лекарств и не заменяет консультацию врача.</p></main>"
    )


def _sub_head(template: str, head: str) -> str:
    template = re.sub(r"\s*<title>.*?</title>", "", template, flags=re.S)
    template = re.sub(r'\s*<meta name="description"[^>]*>', "", template)
    return template.replace("</head>", head + "\n  </head>", 1)


def render_index(template: str, path: str, base: str, verification: dict[str, str] | None = None) -> str:
    """index.html с мета-тегами под адрес `path`. Закрытые адреса получают noindex."""
    path = normalize(path)
    page = PAGES.get(path)
    if page is None:
        head = (
            f"<title>{SITE} — домашняя аптечка</title>\n"
            '    <meta name="description" content="Домашняя аптечка для всей семьи" />\n'
            '    <meta name="robots" content="noindex, nofollow" />'
        )
        return _sub_head(template, head)
    title, desc, _ = page
    t, d = html.escape(title, quote=True), html.escape(desc, quote=True)
    url = base + path
    parts = [
        f"<title>{t}</title>",
        f'<meta name="description" content="{d}" />',
        '<meta name="robots" content="index, follow" />',
        f'<link rel="canonical" href="{url}" />',
        '<meta property="og:type" content="website" />',
        f'<meta property="og:site_name" content="{SITE}" />',
        '<meta property="og:locale" content="ru_RU" />',
        f'<meta property="og:title" content="{t}" />',
        f'<meta property="og:description" content="{d}" />',
        f'<meta property="og:url" content="{url}" />',
        f'<meta property="og:image" content="{base}/icon-512.png" />',
        '<meta name="twitter:card" content="summary" />',
        f'<meta name="twitter:title" content="{t}" />',
        f'<meta name="twitter:description" content="{d}" />',
    ]
    if path == "/":
        for name, code in (verification or {}).items():
            if code:
                parts.append(f'<meta name="{name}" content="{html.escape(code, quote=True)}" />')
        parts.append(f'<script type="application/ld+json">{_json_ld(base)}</script>')
    out = _sub_head(template, "\n    ".join(parts))
    if path == "/":
        out = out.replace('<div id="root"></div>', f'<div id="root">{_prerender_home()}</div>', 1)
    return out


def robots_txt(base: str) -> str:
    lines = ["User-agent: *", "Allow: /"] + [f"Disallow: {p}" for p in DISALLOW]
    lines += ["", f"Sitemap: {base}/sitemap.xml", f"Host: {base}", ""]
    return "\n".join(lines)


def sitemap_xml(base: str, lastmod: str) -> str:
    urls = "".join(
        f"<url><loc>{base}{p}</loc><lastmod>{lastmod}</lastmod><priority>{pr}</priority></url>"
        for p, (_, _, pr) in PAGES.items()
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
