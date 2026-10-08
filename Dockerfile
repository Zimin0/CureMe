# 1) собираем фронтенд
FROM node:26-alpine AS web
# Какой коммит собираем и когда: деплой передаёт их через --build-arg, они видны в /api/version
# и внизу раздела «Семья». Без аргументов сборка тоже работает, просто без коммита.
ARG CUREME_COMMIT=""
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY VERSION /VERSION
COPY frontend/ ./
RUN CUREME_COMMIT="$CUREME_COMMIT" npm run build

# 2) Python-сервер, который отдаёт и API, и собранный фронтенд
FROM python:3.12-slim
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 CUREME_DATABASE_URL=sqlite:////data/cureme.db CUREME_MEDIA_DIR=/data/media CUREME_FRONTEND_DIST=/app/frontend/dist
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Приложение работает не от root: если в нём найдут дыру, взломщик не станет хозяином контейнера.
# start.sh стартует от root только чтобы отдать папку /data этому пользователю, и сразу сбрасывает права.
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app
COPY VERSION /app/VERSION
COPY backend/ ./
ARG CUREME_COMMIT=""
ARG CUREME_BUILT_AT=""
ENV CUREME_COMMIT=$CUREME_COMMIT CUREME_BUILT_AT=$CUREME_BUILT_AT
COPY --from=web /web/dist /app/frontend/dist
VOLUME /data
EXPOSE 8000
CMD ["sh", "start.sh"]
