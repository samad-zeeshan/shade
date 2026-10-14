"""Liljegren WBGT on the demo weather: sanity bands, shade effect, and mean radiant temperature."""
import json
import tempfile
from pathlib import Path

import pytest

from shade.sun import sun_table
from shade.wbgt import load_weather, wbgt_rest, wbgt_table

WEATHER = Path(__file__).resolve().parents[1] / "data" / "weather.json"


@pytest.fixture(scope="module")
def table():
    w, sun = load_weather(WEATHER), sun_table()
    (sunny, shady), (tr_sun, tr_shade) = wbgt_table([[0.0] * 60, [1.0] * 60], w, sun)
    return w, sun, sunny, shady, tr_sun, tr_shade


def test_bands(table):
    _, _, sunny, shady, _, _ = table
    assert 34 <= sunny[32] <= 36          # 13:00 full sun
    assert 31.5 <= shady[32] <= 33        # 13:00 full shade
    assert 27.5 <= shady[4] <= 30         # 06:00 in shade
    assert sunny[4] > shady[4]


def test_shade_and_night(table):
    w, sun, sunny, shady, tr_sun, tr_shade = table
    assert all(a >= b for a, b in zip(sunny, shady))
    night = [s for s in range(60) if sun[s]["elevation"] <= 1]
    assert night and all(sunny[s] == shady[s] for s in night)
    assert tr_sun[32] > tr_shade[32] > w[32]["ta"]


def test_rest_is_full_shade(table):
    w, sun, _, shady, _, _ = table
    assert wbgt_rest(w, sun) == shady


def test_extra_fields_pass_through():
    rows = [{"hour": h, "ta_c": 30, "rh_pct": 50, "wind_ms": 2, "ghi_wm2": 500, "dir": 400, "dif": 100,
             "pressure": 1000} for h in range(5, 21)]
    p = Path(tempfile.mkdtemp()) / "w.json"
    p.write_text(json.dumps({"date": "2026-07-15", "hourly": rows}))
    w = load_weather(p)
    assert w[10]["dir"] == 400 and w[10]["dif"] == 100 and w[10]["pressure"] == 1000
