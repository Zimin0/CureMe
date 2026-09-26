from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import assist, auth, categories, families, medicines

settings = get_settings()
app = FastAPI(title="CureMe", version="1.0.0", description="Домашняя аптечка для всей семьи")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
for r in (auth, families, categories, medicines, assist):
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
