import random

import pytest

from matnyab.services import convert_digits, normalize_text

FA = "۰۱۲۳۴۵۶۷۸۹"
AR = "٠١٢٣٤٥٦٧٨٩"
ASC = "0123456789"
ALPHABET = list("abcXYZ 019١٢۳۴.,%٫٬٪\n-يىكـ\u00a0\u200cیک\u064e") + ["COVID19", "A1", " 1,234 ", "3.14"]


def _rand(rng, n=30):
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, n)))


def test_keep_is_identity():
    assert convert_digits("a1 ۲ ٣", "keep") == "a1 ۲ ٣"


def test_unknown_style():
    with pytest.raises(ValueError):
        convert_digits("1", "xx")  # type: ignore[arg-type]


def test_fa_digits_and_separators():
    assert convert_digits("12", "fa") == "۱۲"
    assert convert_digits("٠١٢", "fa") == "۰۱۲"
    assert convert_digits("3.14", "fa") == "۳٫۱۴"
    assert convert_digits("1,234,567", "fa") == "۱٬۲۳۴٬۵۶۷"
    assert convert_digits("1,2345", "fa") == "۱,۲۳۴۵"
    assert convert_digits("1,23", "fa") == "۱,۲۳"
    assert convert_digits("50%", "fa") == "۵۰٪"
    assert convert_digits("% 5", "fa") == "% ۵"
    assert convert_digits("end. 5, x", "fa") == "end. ۵, x"
    assert convert_digits(".5 and 5.", "fa") == ".۵ and ۵."


def test_fa_leaves_latin_identifiers():
    assert convert_digits("COVID19 و A1", "fa") == "COVID19 و A1"
    assert convert_digits("سال 1400 و COVID19", "fa") == "سال ۱۴۰۰ و COVID19"
    assert convert_digits("v1.2", "fa") == "v1.2"
    assert convert_digits("A1%", "fa") == "A1%"


def test_en():
    assert convert_digits("۱۲۳ ٤٥٦ ۳٫۱۴ ۱٬۰۰۰ ۵۰٪", "en") == "123 456 3.14 1,000 50%"


def test_fa_en_round_trip_digit_strings():
    rng = random.Random(1)
    for _ in range(200):
        s = "".join(rng.choice(ASC) for _ in range(rng.randint(0, 12)))
        fa = convert_digits(s, "fa")
        assert all(c in FA for c in fa)
        assert convert_digits(fa, "en") == s
        assert convert_digits(convert_digits(s, "en"), "fa") == fa


@pytest.mark.parametrize("style", ["fa", "en"])
def test_digits_idempotent_and_only_expected_changes(style):
    rng = random.Random(2)
    allowed = set(ASC + AR + FA + ".,%٫٬٪")
    for _ in range(500):
        s = _rand(rng)
        once = convert_digits(s, style)
        assert convert_digits(once, style) == once
        assert len(once) == len(s)
        for a, b in zip(s, once):
            if a != b:
                assert a in allowed and b in allowed


def test_normalize_mapping():
    assert normalize_text("ي ى ك") == "ی ی ک"
    assert normalize_text("مـتـن") == "متن"
    assert normalize_text("a\u00a0b") == "a b"
    keep = "می\u200cخواهم\u064e hello\r\nline\n"
    assert normalize_text(keep) == keep
    assert normalize_text("") == ""


def test_normalize_idempotent_and_only_expected_changes():
    rng = random.Random(3)
    changed = set("يىكـ\u00a0")
    for _ in range(500):
        s = _rand(rng)
        once = normalize_text(s)
        assert normalize_text(once) == once
        # removing the changed chars from both must leave identical text
        strip = lambda t: "".join(c for c in t if c not in changed and c not in "یک ")
        assert strip(s) == strip(once)
        assert "\u200c" not in s or s.count("\u200c") == once.count("\u200c")
