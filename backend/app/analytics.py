"""Яндекс Метрика: номер счётчика и адреса, которые ему разрешает политика безопасности (CSP).

Счётчик подключается только если задан CUREME_METRIKA_ID. Сам скрипт браузер грузит уже после согласия
посетителя на аналитические cookie (frontend/src/analytics.ts), а без номера в настройках этих адресов
в политике нет вовсе: каждый разрешённый чужой адрес был бы лишней лазейкой для XSS.
"""

import re

from .config import get_settings

# Адреса, которые нужны самому счётчику: скрипт, отправка данных и пиксель. Вебвизор и фреймы не включаем.
METRIKA_CSP = {
    "script-src": ["https://mc.yandex.ru"],
    "connect-src": ["https://mc.yandex.ru", "https://mc.yandex.com"],
    "img-src": ["https://mc.yandex.ru"],
}


def metrika_counter_id() -> str | None:
    """Номер счётчика или None. Принимаем только цифры: значение попадает в адрес скрипта на странице."""
    value = get_settings().metrika_id.strip()
    return value if re.fullmatch(r"\d{4,12}", value) else None
