from datetime import date

from app.codes import GS, display_code, parse_code


def test_ean13():
    p = parse_code("4601669002013")
    assert p.kind == "ean13" and p.gtin == "04601669002013"
    assert display_code(p.gtin) == "4601669002013"


def test_bad_check_digit():
    assert parse_code("4601669002014").kind == "unknown"


def test_mdlp_datamatrix_with_gs():
    raw = f"0104601669002013211ABCDEFGHIJKL{GS}17270531{GS}10AB1234{GS}91EE06{GS}92abc="
    p = parse_code(raw)
    assert p.kind == "datamatrix"
    assert p.gtin == "04601669002013"
    assert p.serial == "1ABCDEFGHIJKL"
    assert p.expiry == date(2027, 5, 31)
    assert p.batch == "AB1234"


def test_mdlp_without_separators_uses_13_char_serial():
    p = parse_code("01046016690020132112345ABCDEFGH91EE0692abcdef")
    assert p.serial == "12345ABCDEFGH"


def test_expiry_day_zero_means_end_of_month():
    p = parse_code(f"0104601669002013{GS}17260200")
    assert p.expiry == date(2026, 2, 28)


def test_human_readable_form():
    p = parse_code("(01)04601669002013(21)SERIAL123(17)281231")
    assert p.serial == "SERIAL123" and p.expiry == date(2028, 12, 31)


# --- дополнительные случаи -----------------------------------------------------

import pytest
from hypothesis import given, strategies as st

from app.codes import _parse_expiry, gtin_check_ok, to_gtin14


def with_check_digit(body: str) -> str:
    """Дописывает к цифрам правильную контрольную цифру GS1 (как делает производитель)."""
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


@pytest.mark.parametrize("code, ok", [
    ("4601669002013", True),     # EAN-13
    ("96385074", True),          # EAN-8
    ("036000291452", True),      # UPC-A (12 цифр)
    ("04601669002013", True),    # GTIN-14
    ("4601669002014", False),    # неверная контрольная цифра
    ("460166900201", False),     # 12 цифр, но это обрезанный EAN-13
    ("12345", False),            # неподходящая длина
    ("46016690020a3", False),    # не цифры
    ("", False),
])
def test_gtin_check_digit(code, ok):
    assert gtin_check_ok(code) is ok


@pytest.mark.parametrize("raw, kind", [
    ("96385074", "ean8"),
    ("036000291452", "ean13"),
    ("04601669002013", "gtin"),
    ("  4601669002013 \n", "ean13"),     # пробелы и перевод строки от сканера
    ("4601 669 002 013", "ean13"),       # цифры, разбитые пробелами, как на упаковке
])
def test_plain_barcodes(raw, kind):
    p = parse_code(raw)
    assert p.kind == kind
    assert p.gtin is not None and len(p.gtin) == 14


@pytest.mark.parametrize("prefix", ["]d2", "]C1", "]Q3", "]E0"])
def test_symbology_prefix_is_ignored(prefix):
    p = parse_code(f"{prefix}0104601669002013215ABCDEFGHIJKL{GS}17270531")
    assert p.kind == "datamatrix" and p.serial == "5ABCDEFGHIJKL"


@pytest.mark.parametrize("sep", ["<GS>", "\\x1d"])
def test_gs_written_as_text(sep):
    """zxing и некоторые приложения отдают GS не символом, а текстом."""
    p = parse_code(f"0104601669002013215ABCDEFGHIJKL{sep}17270531{sep}10SERIES")
    assert p.expiry == date(2027, 5, 31) and p.batch == "SERIES"


@pytest.mark.parametrize("yymmdd, expected", [
    ("270531", date(2027, 5, 31)),
    ("240200", date(2024, 2, 29)),   # «00» в високосном феврале
    ("271300", None),                # 13-й месяц
    ("270000", None),                # нулевой месяц
    ("270231", None),                # 31 февраля
    ("27053", None),                 # короткая строка
    ("27O531", None),                # буква вместо цифры
])
def test_parse_expiry(yymmdd, expected):
    assert _parse_expiry(yymmdd) == expected


def test_bad_expiry_does_not_break_the_rest():
    p = parse_code(f"0104601669002013215ABCDEFGHIJKL{GS}17271399")
    assert p.kind == "datamatrix" and p.serial == "5ABCDEFGHIJKL" and p.expiry is None


def test_unknown_ai_stops_parsing_but_keeps_known_fields():
    p = parse_code(f"0104601669002013{GS}99SOMETHING{GS}10BATCH")
    assert p.gtin == "04601669002013" and p.batch is None


def test_datamatrix_with_wrong_gtin_check_is_unknown():
    assert parse_code(f"0104601669002014215ABCDEFGHIJKL{GS}17270531").kind == "unknown"


@pytest.mark.parametrize("raw", ["", "hello", "https://example.com/?q=1", "01", "(01)", "0" * 600])
def test_garbage_is_unknown(raw):
    p = parse_code(raw)
    assert p.kind == "unknown" and p.gtin is None


def test_to_dict_serializes_expiry():
    d = parse_code(f"0104601669002013215ABCDEFGHIJKL{GS}17270531").to_dict()
    assert d["expiry"] == "2027-05-31" and d["kind"] == "datamatrix"
    assert parse_code("4601669002013").to_dict()["expiry"] is None


def test_display_code():
    assert display_code(None) is None
    assert display_code("14601669002010") == "14601669002010"  # GTIN-14 без ведущего нуля остаётся как есть


# --- property-based: проверяем свойства на сотнях случайных входов -------------

@given(st.text(max_size=200))
def test_parse_code_never_crashes(raw):
    p = parse_code(raw)
    assert p.kind in {"datamatrix", "ean13", "ean8", "gtin", "unknown"}
    if p.gtin:
        assert len(p.gtin) == 14 and gtin_check_ok(p.gtin)


@given(st.text(alphabet="0123456789", min_size=12, max_size=12))
def test_any_ean13_with_valid_check_digit_is_recognized(body):
    ean = with_check_digit(body)
    p = parse_code(ean)
    assert p.kind == "ean13" and p.gtin == to_gtin14(ean) and display_code(p.gtin).lstrip("0") == ean.lstrip("0")


@given(
    st.text(alphabet="0123456789", min_size=13, max_size=13),
    st.text(alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", min_size=13, max_size=13),
    st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
)
def test_mdlp_roundtrip(gtin_body, serial, expiry):
    """Собираем код «Честного знака» из частей и проверяем, что парсер достаёт их обратно."""
    gtin = with_check_digit(gtin_body)
    raw = f"01{gtin}21{serial}{GS}17{expiry:%y%m%d}{GS}91EE06{GS}92crypto="
    p = parse_code(raw)
    assert (p.kind, p.gtin, p.serial, p.expiry) == ("datamatrix", gtin, serial, expiry)
