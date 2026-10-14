"""NIOSH REL as a 1-hour average, turned into a load per slot."""
import math

from shade.limits import BUDGET, M, M_REST, WORK_MIN, load, rel


def test_rel_formula():
    assert math.isclose(rel(300), 56.7 - 11.5 * math.log10(300))
    assert 28.1 < rel(300) < 28.3


def test_full_rate_when_cool():
    assert load(25.0, 25.0, "very_heavy") == 12
    assert WORK_MIN[load(25.0, 25.0, "light")] == 60


def test_worked_check():
    # Moderate work at 30 C WBGT in sun, rest at 27 C in shade: half the hour is the most that fits.
    wbgt_twa = 0.5 * 30 + 0.5 * 27
    assert wbgt_twa <= rel(0.5 * M["moderate"] + 0.5 * M_REST)
    assert load(30.0, 27.0, "moderate") == 24
    assert BUDGET // 24 == 2


def test_forbidden():
    assert load(34.4, 32.0, "heavy") is None
    assert WORK_MIN[None] == 0
