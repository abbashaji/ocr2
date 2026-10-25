"""Pure-function tests for the ported helpers."""

from __future__ import annotations

from matnyab.engine import lexicon, scoring
from matnyab.engine.markers import Char, HWord, clean_words_conf, marker_flags
from matnyab.engine.tesseract_engine import choose_mode
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
    assert restore_placeholders("12,34") == "12،34"   # not a thousands group
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
