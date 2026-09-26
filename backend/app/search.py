"""Подбор лекарств под болезнь.

Без внешних сервисов: нормализуем текст, отрезаем окончания (грубый «стемминг»),
расширяем запрос синонимами и сравниваем с показаниями, категорией и названием.
"""

import re

from .seed import CONDITION_SYNONYMS

STOP_WORDS = {
    "от", "при", "для", "и", "у", "в", "во", "на", "с", "со", "по", "меня", "мне", "что",
    "делать", "сильная", "сильный", "сильно", "очень", "немного", "чем", "как", "лечить",
}


def normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").lower().replace("ё", "е"))


def stem(token: str) -> str:
    return token if len(token) <= 3 else token[: max(3, len(token) - 2)]


def stems(text: str) -> list[str]:
    return [stem(t) for t in normalize(text).split() if t not in STOP_WORDS and len(t) >= 2]


def _stem_match(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def phrase_coverage(phrase_stems: list[str], text_stems: list[str]) -> float:
    """Доля слов фразы, которые нашлись в тексте (0..1)."""
    if not phrase_stems or not text_stems:
        return 0.0
    hit = sum(1 for p in phrase_stems if any(_stem_match(p, t) for t in text_stems))
    return hit / len(phrase_stems)


def expand_query(query: str) -> list[tuple[str, float]]:
    """Возвращает фразы для поиска с весом: сам запрос — 1.0, синонимы — 0.8."""
    q_stems = stems(query)
    phrases: list[tuple[str, float]] = [(query, 1.0)]
    for group in CONDITION_SYNONYMS:
        if any(phrase_coverage(stems(p), q_stems) == 1.0 or phrase_coverage(q_stems, stems(p)) == 1.0 for p in group):
            phrases += [(p, 0.8) for p in group if normalize(p).strip() != normalize(query).strip()]
    return phrases


def best_match(phrases: list[tuple[str, float]], text: str) -> tuple[float, str | None]:
    text_stems = stems(text)
    best, which = 0.0, None
    for phrase, weight in phrases:
        cov = phrase_coverage(stems(phrase), text_stems)
        if cov >= 0.99 or (cov >= 0.5 and len(stems(phrase)) > 1):
            score = cov * weight
            if score > best:
                best, which = score, phrase
    return best, which
