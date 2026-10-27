"""Pure-function tests for the ported helpers."""

from __future__ import annotations

import pytest

from matnyab.engine import lexicon, scoring
from matnyab.engine.markers import Char, HWord, clean_words_conf, marker_flags
from matnyab.engine.tesseract_engine import _pick_scale, _unbalanced_brackets, choose_mode
from matnyab.engine.textfix import finalize_tok, restore_placeholders


def _c(ch: str, x: int, y0: int, y1: int, wc: float = 90.0) -> Char:
    return Char(ch, x, y0, x + 8, y1, wc, wc)


def _word_with_marker() -> list[Char]:
    # 4 base letters on the baseline (y 100..120), then a raised "[۱]" (bottom at 108)
    base = [_c("س", 0, 100, 120), _c("ل", 10, 100, 120), _c("ا", 20, 100, 120), _c("م", 30, 100, 120)]
    sup = [_c("[", 40, 96, 108), _c("۱", 48, 98, 108), _c("]", 56, 96, 108)]
    return base + sup


def test_marker_flags_flags_raised_bracketed_digits():
    flags = marker_flags([_word_with_marker()])
    assert flags == [[False] * 4 + [True] * 3]


def test_marker_flags_keeps_normal_digits_on_baseline():
    w = [_c("س", 0, 100, 120), _c("ل", 10, 100, 120), _c("ا", 20, 100, 120), _c("م", 30, 100, 120),
         _c("۱", 40, 100, 120), _c("۲", 48, 100, 120)]
    assert marker_flags([w]) == [[False] * 6]


def test_marker_flags_too_little_text_flags_nothing():
    w = [_c("س", 0, 100, 120), _c("۱", 10, 90, 100)]
    assert marker_flags([w]) == [[False, False]]


def test_clean_words_conf_removes_marker_and_shrinks_box():
    chars = tuple(_word_with_marker())
    word = HWord(chars, 91.0, (0, 96, 64, 120))
    (tok,) = clean_words_conf([word])
    assert tok.text == "سلام"
    assert tok.conf == 90.0  # confidence of the first kept character's word
    assert tok.box == (0, 100, 38, 120)
    (kept,) = clean_words_conf([word], remove_markers=False)
    assert kept.text == "سلام[۱]" and kept.box == (0, 96, 64, 120)


def test_clean_words_conf_drops_empty_words():
    base = [_c("س", 0, 100, 120), _c("ل", 10, 100, 120), _c("ا", 20, 100, 120), _c("م", 30, 100, 120)]
    only_marker = [_c("[", 0, 96, 108), _c("۱", 8, 98, 108), _c("]", 16, 96, 108)]
    toks = clean_words_conf([HWord(tuple(base), 90, None), HWord(tuple(only_marker), 90, None)])
    assert [t.text for t in toks] == ["سلام"]


def test_finalize_tok():
    assert finalize_tok("سلامء") == "سلام،"        # glued hamza at word end -> comma
    assert finalize_tok("سلام,") == "سلام،"
    assert finalize_tok("چرا?") == "چرا؟"
    assert finalize_tok("ءاب") == "ءاب"            # word-initial hamza is untouched


def test_restore_placeholders():
    assert restore_placeholders("1.64") == "1٫64"
    assert restore_placeholders("۱.۶۴") == "۱٫۶۴"
    assert restore_placeholders("12,345") == "12٬345"
    assert restore_placeholders("12,34") == "12٫34"   # not a thousands group: a decimal mark (client "۱٫۶۴")
    assert restore_placeholders("a,b") == "a،b"
    assert restore_placeholders("50#") == "50٪"


def test_choose_mode_rule():
    assert choose_mode([10.0] * 19) == "raw"                 # fewer than 20 words
    assert choose_mode([95.0] * 18 + [50.0] * 2) == "lex"    # exactly 10% low
    assert choose_mode([95.0] * 19 + [50.0] * 1) == "raw"    # 5% low
    assert choose_mode([80.0] * 30) == "raw"                 # 80 is not < 80
    assert choose_mode([]) == "raw"


def test_scoring_normalisation():
    assert scoring.base("كتاب\u200cي") == "کتاب ی"           # Arabic letters, ZWNJ -> space
    assert scoring.base("۱۲٣") == "123"
    assert scoring.base("سَلام\u200f") == "سلام"              # diacritic and RLM removed
    assert scoring.words("سلام، دنیا! 12") == ["سلام", "دنیا", "12"]
    assert scoring.words("می\u200cروم") == ["می", "روم"]     # ZWNJ counts as a space


def test_strip_markers_and_word_accuracy():
    assert scoring.strip_markers("اصفهان[۲۴۶] و تهران[۱۱]") == "اصفهان و تهران"
    assert scoring.word_accuracy("الف ب ج د", "الف ب ج د") == 1.0
    assert scoring.word_accuracy("الف ب ج د", "الف ب ج") == 0.75
    assert scoring.word_accuracy("", "") == 1.0


def test_lexicon_correct_tok_respects_conf_skip():
    assert lexicon.correct_tok("سلامم", 95, **lexicon.RAW_CONFIG) == "سلامم"  # conf_skip=0: untouched
    assert lexicon.correct_tok("ab", 10, **lexicon.LEX_CONFIG) == "ab"        # not Persian letters
    assert lexicon.correct_tok("سلامم", 95, **lexicon.LEX_CONFIG) == "سلامم"  # >= conf_skip 90


def test_fix_final_kaf_repairs_unknown_words_whatever_the_confidence():
    # Tesseract reads a final "ی" as "ک" with confidence >= 90, so correct_tok never sees these.
    assert lexicon.fix_final_kaf("کشورک") == "کشوری"
    assert lexicon.fix_final_kaf("جاک") == "جای"
    assert lexicon.fix_final_kaf("ادارک") == "اداری"
    assert lexicon.fix_final_kaf("تمدن\u200cهاک") == "تمدن\u200cهای"


def test_fix_final_kaf_leaves_known_words_and_other_text_alone():
    for word in ("کوچک", "پاک", "اندک", "مبارک", "ab", "هاک", "کشوری", "۱۲۳"):
        assert lexicon.fix_final_kaf(word) == word


def _line(*extra):
    return [_c("س", 0, 100, 120), _c("ل", 10, 100, 120), _c("ا", 20, 100, 120), _c("م", 30, 100, 128), *extra]


def test_marker_flags_keeps_a_standalone_number_even_when_it_measures_as_raised():
    # "۳۱" sits on the baseline but, with descenders pulling the median bottom down, looks ~0.35 raised.
    line = _line(_c("ر", 40, 100, 130), _c("ز", 50, 100, 130))
    number = [_c("۳", 0, 104, 120), _c("۱", 8, 104, 120)]
    flags = marker_flags([line, number])
    assert flags[1] == [False, False]


def test_marker_flags_keeps_the_leading_digit_of_a_decimal_number():
    line = _line(_c("ر", 40, 100, 130), _c("ز", 50, 100, 130))
    decimal = [_c("۱", 0, 104, 120), _c(".", 8, 116, 120), _c("۶", 16, 100, 120), _c("۴", 24, 100, 120)]
    assert marker_flags([line, decimal])[1] == [False] * 4


def test_marker_flags_keeps_a_barely_raised_number_glued_to_a_conjunction():
    line = _line(_c("ر", 40, 100, 130), _c("ز", 50, 100, 130))
    glued = [_c("و", 0, 100, 120), _c("۳", 8, 104, 120), _c("۱", 16, 104, 120)]
    assert marker_flags([line, glued])[1] == [False] * 3


def test_marker_flags_still_removes_a_clearly_raised_unbracketed_superscript():
    line = _line()
    word = [_c("س", 0, 100, 120), _c("ل", 10, 100, 120), _c("ا", 20, 100, 120), _c("م", 30, 100, 120),
            _c("۱", 40, 90, 98)]
    assert marker_flags([line, word])[1] == [False] * 4 + [True]


def test_restore_placeholders_comma_between_digits_is_decimal_unless_a_thousands_group():
    assert restore_placeholders("۱,۶۴") == "۱٫۶۴"
    assert restore_placeholders("۱،۶۴") == "۱٫۶۴"
    assert restore_placeholders("۱,۶۴۰") == "۱٬۶۴۰"      # exactly three digits: thousands
    assert restore_placeholders("سلام,") == "سلام،"        # a plain comma after a letter is untouched
    assert restore_placeholders("۱۲, ۳") == "۱۲، ۳"        # a list with a space is untouched


def test_restore_placeholders_drops_a_stray_stop_before_a_comma():
    assert restore_placeholders("خط.,") == "خط،"
    assert restore_placeholders("خط.،") == "خط،"
    assert restore_placeholders("است.") == "است."          # a real full stop stays


def test_finalize_tok_normalises_arabic_indic_digits_and_drops_bidi_marks():
    assert finalize_tok("٩۲\u200f") == "۹۲"
    assert finalize_tok("\u200eسلام") == "سلام"


# ---- lexicon never shortens a word ---------------------------------------------------------------------------


def test_lexicon_never_deletes_letters():
    cfg = lexicon.LEX_CONFIG
    # Fragment of "به‌تدریج" (the word box was split): the old rule dropped the "ت" -> "به‌در".
    out = lexicon.correct_tok("به‌تدر", 50, **cfg)
    assert len(out) >= len("به‌تدر") and out != "به‌در"
    for frag in ("معالی", "مشاهد", "ستاید", "تشرع"):  # deletions the lexicon used to make (all wrong on real data)
        assert len(lexicon.correct_tok(frag, 50, **cfg)) >= len(frag)


def test_lexicon_still_substitutes_and_inserts():
    cfg = lexicon.LEX_CONFIG
    assert lexicon.correct_tok("حایز", 50, **cfg) == "جایز"            # substitution
    assert lexicon.correct_tok("شهرنشین", 50, **cfg) == "شهرنشینی"     # insertion
    assert lexicon.correct_tok("لاجورد", 50, **cfg) == "لاجوردی"


# ---- scale selection avoids stray brackets ------------------------------------------------------------------


def test_unbalanced_brackets():
    assert _unbalanced_brackets("و با ۹]")
    assert _unbalanced_brackets("و با ]۹")
    assert not _unbalanced_brackets("و با ۹۲")
    assert not _unbalanced_brackets("اصفهان[۲۴۶] و تهران")


def test_pick_scale_prefers_balanced_reading():
    texts = ["و با ۹]", "و با ۹]", "و با ۹]", "و با ۹۲", "و با ۹۲"]
    assert _pick_scale(texts) in (3, 4)            # the plain medoid would be a "۹]" reading
    assert _pick_scale(["و با ۹]", "و با ۹]"]) in (0, 1)   # no balanced reading: fall back to the medoid
    assert _pick_scale(["الف ب", "الف ج", "الف ب"]) in (0, 2)  # no brackets at all: plain medoid


# ---- numbers / punctuation scoring --------------------------------------------------------------------------


def test_numbers_and_puncts():
    assert scoring.numbers("۱٫۶۴ و ۳۱ و ۱٬۲۳۴") == ["1.64", "31", "1,234"]
    assert scoring.puncts("سلام، دنیا. (۱٫۶)") == "،.(٫)"


def test_numbers_f1_sees_wrong_separator_and_lost_digit():
    ref = "مساحت ۱٫۶۴ میلیون و ۳۱ و ۹۲"
    assert scoring.numbers_f1(ref, ref) == 1.0
    assert scoring.numbers_f1(ref, ref.replace("۱٫۶۴", "۱،۶۴")) == pytest.approx(2 / 3)   # decimal mark misread
    assert scoring.numbers_f1(ref, ref.replace("۹۲", "۹]")) == pytest.approx(2 / 3)
    assert scoring.numbers_f1(ref, ref.replace(" و ۳۱", "")) == pytest.approx(0.8)         # a lost number
    assert scoring.numbers_f1("بدون عدد", "هیچ") is None


def test_punct_f1_sees_comma_for_full_stop():
    assert scoring.punct_f1("الف، ب. ج.", "الف، ب. ج.") == 1.0
    assert scoring.punct_f1("الف، ب. ج.", "الف، ب، ج.") == pytest.approx(2 * 2 / 6)
    assert scoring.punct_f1("الف ب", "الف ب") is None
