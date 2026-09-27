"""Ограничение частоты запросов (rate limiting) без внешних сервисов.

Защищает вход и регистрацию от перебора паролей, а коды приглашений — от угадывания.
Счётчики живут в памяти процесса: на сервере один процесс uvicorn, этого хватает.
После перезапуска счётчики обнуляются — это нормально.
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from .config import get_settings


class Limiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> None:
        """Засчитывает попытку; если за `window` секунд их больше `limit`, отвечает 429."""
        if not get_settings().rate_limit:
            return
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                retry = int(q[0] + window - now) + 1
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Слишком много попыток. Подождите немного и попробуйте снова.",
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)
            if len(self._hits) > 50_000:  # не даём словарю расти бесконечно
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - 3600}

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = Limiter()


def client_ip(request: Request) -> str:
    # За Caddy настоящий адрес приходит в X-Forwarded-For; uvicorn подставляет его сам,
    # если прокси доверенный (FORWARDED_ALLOW_IPS в docker-compose.prod.yml).
    return request.client.host if request.client else "unknown"
