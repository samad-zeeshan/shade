"""Parse a saved Open-Meteo response into the weather.json shape, with no network."""
import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from shade.weather import ARCHIVE_URL, URL, check_date, endpoint, parse
from shade.wbgt import load_weather

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_2026-10-14.json"


def test_parse_fixture():
    d = parse(json.loads(FIXTURE.read_text(encoding="utf-8")), "2026-10-14", fetched="2026-10-14T10:00:00+00:00")
    assert d["date"] == "2026-10-14" and d["source"] == "Open-Meteo forecast, fetched 2026-10-14T10:00:00+00:00"
    rows = d["hourly"]
    assert [r["hour"] for r in rows] == list(range(5, 21))
    assert set(rows[0]) == {"hour", "ta_c", "rh_pct", "wind_ms", "ghi_wm2", "dir", "dif", "pressure"}
    assert max(r["ghi_wm2"] for r in rows) > 300 and rows[-1]["ghi_wm2"] == 0


def test_parsed_rows_load():
    d = parse(json.loads(FIXTURE.read_text(encoding="utf-8")), "2026-10-14")
    p = Path(tempfile.mkdtemp()) / "w.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    w = load_weather(p)
    assert len(w) == 60 and {"dir", "dif", "pressure"} <= set(w[20])


def test_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        check_date("2021-12-31")
    with pytest.raises(ValueError, match="out of range"):
        check_date("2099-01-01")


def test_router_picks_archive_for_old_dates():
    today = date(2026, 10, 14)
    assert endpoint("2025-07-15", today) == (ARCHIVE_URL, "Open-Meteo archive (ERA5)")
    assert endpoint("2026-10-10", today)[0] == URL
    assert endpoint("2026-10-20", today)[0] == URL
