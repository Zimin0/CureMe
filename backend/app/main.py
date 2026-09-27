from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import admin, assist, auth, categories, families, files, medicines

settings = get_settings()
docs = settings.api_docs  # на сервере выключено: незачем показывать всем карту API
app = FastAPI(
    title="Капсулка", version="1.0.0", description="Домашняя аптечка для всей семьи",
    docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Content Security Policy: браузер выполняет только наши скрипты, так что даже если в название
# лекарства подсунут <script>, он не запустится и не утащит токен входа.
# wasm-unsafe-eval и blob: нужны сканеру штрихкодов (zxing-wasm) и распознаванию срока (tesseract).
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'wasm-unsafe-eval' blob:",
    "worker-src 'self' blob:",
    "connect-src 'self' data: blob:",
    "img-src 'self' data: blob:",
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if not request.url.path.startswith(("/docs", "/redoc")):  # Swagger UI грузит скрипты с CDN
        response.headers.setdefault("Content-Security-Policy", CSP)
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/media/"):
        response.headers.setdefault("Cache-Control", "no-store")  # ответы API с данными семьи не кешируем
    return response


for r in (auth, families, categories, medicines, assist, files, admin):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Собранный фронтенд отдаём тем же сервером: одно приложение — один адрес.
dist = settings.frontend_dist
if dist.is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = (dist / path).resolve()
        if path and file.is_file() and dist.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(dist / "index.html")
