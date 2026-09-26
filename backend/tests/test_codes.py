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
