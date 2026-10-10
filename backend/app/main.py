from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import reminders, seo
from .config import get_settings
from .db import SessionLocal
from .routers import admin, assist, auth, categories, families, files, illness, intakes, medicines, notifications, payments, reports, schedule, schedule_notify
from .version import app_version

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Фоновые потоки: ежедневные напоминания и Telegram-бот (см. reminders.py). В тестах выключены.
    stop = reminders.start_background(SessionLocal) if settings.background_jobs else None
    yield
    if stop:
        stop.set()


docs = settings.api_docs  # на сервере выключено: незачем показывать всем карту API
app = FastAPI(
    title="Капсулка", version=app_version()["version"], description="Домашняя аптечка для всей семьи",
    docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None, lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Content Security Policy: браузер выполняет только наши скрипты, так что даже если в название
# лекарства подсунут <script>, он не запустится и не утащит токен входа.
# wasm-unsafe-eval и blob: нужны сканеру штрихкодов (zxing-wasm) и распознаванию срока (tesseract).
# Оплата идёт переходом на страницу ЮKassa целиком (сайт её не встраивает), поэтому скриптов, фреймов и запросов
# к ЮKassa страница не загружает и в политике их нет: каждый разрешённый чужой адрес был бы лишней лазейкой для XSS.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'wasm-unsafe-eval' blob:",
    "worker-src 'self' blob:",
    "connect-src 'self' data: blob:",
    "img-src 'self' data: blob:",
    "frame-src 'none'",
    "media-src 'self' blob:",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",     # не угадывать тип файла: картинка не станет скриптом
    "X-Frame-Options": "DENY",               # сайт нельзя встроить в чужую страницу (clickjacking)
    "Referrer-Policy": "same-origin",        # код приглашения из адреса не уйдёт на чужие сайты
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


SHELL_FILES = {"/sw.js", "/registerSW.js", "/manifest.webmanifest", "/index.html"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if not request.url.path.startswith(("/docs", "/redoc")):  # Swagger UI грузит скрипты с CDN
        response.headers.setdefault("Content-Security-Policy", CSP)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")  # имена файлов с хешем: не меняются
    elif not path.startswith(("/api/", "/ocr/")) and (path in SHELL_FILES or not Path(path).suffix):
        # Оболочка приложения: страница и service worker всегда проверяются на сервере, иначе браузер
        # (или прокси) покажет старую версию после выката.
        response.headers.setdefault("Cache-Control", "no-cache")
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/media/"):
        response.headers.setdefault("Cache-Control", "no-store")  # ответы API с данными семьи не кешируем
    return response


for r in (auth, families, categories, medicines, intakes, illness, assist, files, reports, admin, notifications, payments, schedule, schedule_notify):
    app.include_router(r.router)
app.include_router(schedule_notify.public)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/version")
def version():
    """Какая версия работает на сервере: номер из VERSION, коммит и время сборки (их задаёт деплой)."""
    return app_version()


def _base(request: Request) -> str:
    return seo.base_url(settings.public_url, str(request.base_url))


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request):
    return Response(seo.robots_txt(_base(request)), media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request):
    built = (app_version()["built_at"] or "")[:10] or date.today().isoformat()
    return Response(seo.sitemap_xml(_base(request), built), media_type="application/xml")


# Собранный фронтенд отдаём тем же сервером: одно приложение — один адрес.
dist = settings.frontend_dist
if dist.is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        file = (dist / path).resolve()
        if path and file.is_file() and dist.resolve() in file.parents:
            return FileResponse(file)
        # index.html отдаём с мета-тегами под адрес (seo.py): публичные страницы индексируются, остальные нет
        template = (dist / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(seo.render_index(template, path, _base(request), {
            "yandex-verification": settings.yandex_verification, "google-site-verification": settings.google_verification,
        }))
