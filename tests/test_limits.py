"""Work fraction lookup and its twelfths-of-an-hour load."""
from shade.limits import BUDGET, load


def test_worked_check():
    assert load(29.5, "moderate") == 24  # 50 percent column
    assert BUDGET // load(29.5, "moderate") == 2
    assert load(30.2, "very_heavy") is None
    assert load(29.5, "very_heavy") == 48  # 25 percent column
    assert BUDGET // 48 == 1


def test_full_rate_and_boundaries():
    assert load(25.0, "light") == 12
    assert load(31.0, "light") == 12
    assert load(31.1, "light") == 24  # 75 percent shares 31.0, so the next step is 50
    assert load(20.0, "heavy") == 16  # heavy never gets 100 percent


def test_forbidden():
    assert load(32.6, "light") is None
    assert load(31.6, "moderate") is None
