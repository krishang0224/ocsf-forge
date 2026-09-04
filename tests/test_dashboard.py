import math

from ulpf.ui.dashboard import safe_parse_rate


def test_empty_parse_rate_is_zero():
    assert safe_parse_rate(None) == 0.0
    assert safe_parse_rate(float("nan")) == 0.0
    assert not math.isnan(safe_parse_rate(float("nan")))


def test_valid_parse_rate_is_preserved():
    assert safe_parse_rate(97.5) == 97.5
