"""WBGT formula against a hand value, and sanity bands on the demo weather."""
from pathlib import Path

import pytest

from shade.wbgt import load_weather, wbgt, wbgt_at

WEATHER = Path(__file__).resolve().parents[1] / "data" / "weather.json"


def test_formula_hand_value():
    # 0.735*40 + 0.0374*40 + 0.00292*1600 + 7.619*0.8 - 4.557*0.64 - 0.0572*3 - 4.064
    assert wbgt(40, 40, 0.8, 3) == pytest.approx(34.5111, abs=1e-3)


@pytest.mark.skipif(not WEATHER.exists(), reason="data/weather.json not present")
def test_bands():
    w = load_weather(WEATHER)
    assert 28 <= wbgt_at(w[4], 0.0) <= 30          # 06:00
    assert 34 <= wbgt_at(w[32], 0.0) <= 36         # 13:00 full sun
    assert 31.5 <= wbgt_at(w[32], 1.0) <= 33       # 13:00 full shade
