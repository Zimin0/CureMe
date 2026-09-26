# 1) собираем фронтенд
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) Python-сервер, который отдаёт и API, и собранный фронтенд
FROM python:3.12-slim
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 CUREME_DATABASE_URL=sqlite:////data/cureme.db CUREME_MEDIA_DIR=/data/media CUREME_FRONTEND_DIST=/app/frontend/dist
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
VOLUME /data
EXPOSE 8000
CMD ["sh", "start.sh"]
