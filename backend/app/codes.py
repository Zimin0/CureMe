"""Разбор кодов с упаковки.

На российских лекарствах обычно два кода:
- EAN-13 — обычный штрихкод, он одинаковый у всех упаковок одного товара;
- DataMatrix «Честного знака» (МДЛП) — квадратный код в формате GS1. В нём
  GTIN товара (AI 01), серийный номер упаковки (21), часто срок годности (17)
  и номер серии (10), плюс криптохвост (91/92), который нам не нужен.
"""

import calendar
import re
from dataclasses import asdict, dataclass
from datetime import date

GS = "\x1d"
# Длины AI с фиксированной длиной данных, которые встречаются на лекарствах.
FIXED = {"01": 14, "02": 14, "11": 6, "13": 6, "15": 6, "17": 6}
VARIABLE = {"10": 20, "21": 20, "91": 90, "92": 90, "93": 90, "240": 30}
MDLP_SERIAL_LEN = 13


@dataclass
class ParsedCode:
    kind: str                    # datamatrix | ean13 | ean8 | gtin | unknown
    raw: str
    gtin: str | None = None      # всегда 14 цифр
    serial: str | None = None
    batch: str | None = None
    expiry: date | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["expiry"] = self.expiry.isoformat() if self.expiry else None
        return d


def gtin_check_ok(digits: str) -> bool:
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def to_gtin14(digits: str) -> str:
    return digits.zfill(14)


def display_code(gtin14: str | None) -> str | None:
    """14-значный GTIN с ведущим нулём показываем как привычный EAN-13."""
    if not gtin14:
        return None
    return gtin14[1:] if gtin14.startswith("0") else gtin14


def _parse_expiry(yymmdd: str) -> date | None:
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    if not 1 <= mm <= 12:
        return None
    year = 2000 + yy
    if dd == 0:  # по стандарту GS1 «00» значит последний день месяца
        dd = calendar.monthrange(year, mm)[1]
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _parse_gs1(data: str) -> dict[str, str]:
    """Разбирает строку GS1 без скобок. Переменные поля заканчиваются символом GS."""
    out: dict[str, str] = {}
    i = 0
    while i < len(data):
        if data[i] == GS:
            i += 1
            continue
        ai = next((a for a in ("240",) if data.startswith(a, i)), None) or data[i : i + 2]
        i += len(ai)
        if ai in FIXED:
            out[ai] = data[i : i + FIXED[ai]]
            i += FIXED[ai]
        elif ai in VARIABLE:
            end = data.find(GS, i)
            if end == -1:
                end = len(data)
                # Сканер потерял разделители GS: у лекарств серийный номер ровно 13 символов.
                if ai == "21" and end - i > MDLP_SERIAL_LEN:
                    end = i + MDLP_SERIAL_LEN
            out[ai] = data[i:end][: VARIABLE[ai]]
            i = end
        else:
            break  # неизвестный AI — дальше разбирать ненадёжно
    return out


def parse_code(raw: str) -> ParsedCode:
    text = raw.strip().replace("\\x1d", GS).replace("<GS>", GS)
    # Префикс символики, который добавляют некоторые сканеры: ]d2, ]C1, ]Q3, ]E0
    text = re.sub(r"^\][A-Za-z]\d", "", text)

    digits = re.sub(r"\s", "", text)
    if digits.isdigit() and len(digits) in (8, 12, 13, 14) and gtin_check_ok(digits):
        kind = {8: "ean8", 12: "ean13", 13: "ean13", 14: "gtin"}[len(digits)]
        return ParsedCode(kind=kind, raw=raw, gtin=to_gtin14(digits))

    # Человекочитаемый вид: (01)04601234567890(21)ABC...
    if text.startswith("("):
        text = GS.join(f"{ai}{val}" for ai, val in re.findall(r"\((\d{2,4})\)([^(]*)", text))

    if text.startswith("01") and len(text) >= 16:
        fields = _parse_gs1(text)
        gtin = fields.get("01")
        if gtin and gtin_check_ok(gtin):
            return ParsedCode(
                kind="datamatrix",
                raw=raw,
                gtin=gtin,
                serial=fields.get("21"),
                batch=fields.get("10"),
                expiry=_parse_expiry(fields["17"]) if "17" in fields else None,
            )
    return ParsedCode(kind="unknown", raw=raw)
