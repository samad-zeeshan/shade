"""Check solar position against known Dubai anchors on the demo day."""
from datetime import datetime, timezone

from shade.sun import LAT, LON, sun_position, sun_table


def at(h, m):
    return sun_position(LAT, LON, datetime(2026, 7, 15, h - 4, m, tzinfo=timezone.utc))


def test_noon():
    assert abs(at(12, 20)[1] - 86) < 1.5


def test_morning():
    az, el = at(6, 0)
    assert 3 - 1.5 <= el <= 8 + 1.5
    assert abs(az - 65) < 1.5 + 2


def test_evening():
    az, el = at(18, 0)
    assert 15 - 1.5 <= el <= 20 + 1.5
    assert abs(az - 290) < 1.5 + 2


def test_sunset_near_1910():
    assert at(19, 0)[1] > 0 > at(19, 20)[1]


def test_table():
    t = sun_table()
    assert len(t) == 60 and t[0]["slot"] == 0
    assert t[29]["elevation"] > 80
