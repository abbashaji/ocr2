import re

from matnyab.ui.queue_panel import confidence_short_label
from matnyab.ui.result_pane import confidence_chip_spec
from matnyab.ui.strings import S

DIGITS = re.compile(r"[0-9\u06f0-\u06f9\u0660-\u0669%\u066a]")


def test_labels_never_contain_a_percentage_or_number():
    for conf in (0, 40, 59.9, 60, 74.9, 75, 84.9, 85, 89.3, 99):
        assert not DIGITS.search(confidence_chip_spec(conf)[0])
        assert not DIGITS.search(confidence_short_label(conf))


def test_clean_page_average_reads_as_high():
    # A near-perfect page averages ~89 with Tesseract's compressed Persian scores.
    assert confidence_chip_spec(89.3)[0] == S.conf_high
    assert confidence_chip_spec(80.0)[0] == S.conf_mid
    assert confidence_chip_spec(50.0)[0] == S.conf_low
