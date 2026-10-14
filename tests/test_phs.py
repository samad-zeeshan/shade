"""PHS run length: no limit for light work early, a hard stop for heavy work at midday."""
from pathlib import Path

from shade.phs import CAP_MIN, run_minutes, run_table
from shade.sun import sun_table
from shade.wbgt import load_weather, wbgt_table

WEATHER = Path(__file__).resolve().parents[1] / "data" / "weather.json"


def test_light_at_six_is_unlimited():
    w = load_weather(WEATHER)
    _, tr = wbgt_table([[0.0] * 60], w, sun_table())
    mins, _ = run_minutes("light", w, tr[0])
    assert mins[4] == CAP_MIN


def test_forbidding_case():
    # Very heavy work in 48 C air and 60 C radiant heat: core temperature reaches 38 C in under 30 minutes,
    # so a second slot in a row on the task is forbidden.
    w = [{"ta": 48.0, "rh": 40, "wind": 0.2}]
    mins, clipped = run_minutes("very_heavy", w, [60.0])
    assert 15 <= mins[0] < 30 and clipped == 0
    _, caps, _ = run_table([{"cls": "very_heavy"}], w, [[60.0]])
    assert caps == [[1]]


def test_clipping_counts():
    # 5 m/s wind is outside the 0 to 3 m/s range of the model, so the cell is clipped, not NaN.
    mins, clipped = run_minutes("heavy", [{"ta": 40.0, "rh": 30, "wind": 5.0}], [50.0])
    assert clipped == 1 and 0 < mins[0] <= CAP_MIN
