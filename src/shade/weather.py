"""
Fetch one day of hourly weather from Open-Meteo in the same shape as data/weather.json.

Recent and future days come from the forecast endpoint, older days from the ERA5 archive.
"""
from datetime import date as Date, datetime, timedelta, timezone

import httpx

from shade.sun import LAT, LON

URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FIELDS = {
    "temperature_2m": "ta_c",
    "relative_humidity_2m": "rh_pct",
    "wind_speed_10m": "wind_ms",
    "shortwave_radiation": "ghi_wm2",
    "direct_radiation": "dir",
    "diffuse_radiation": "dif",
    "surface_pressure": "pressure",
}
FIRST_DAY = Date(2022, 1, 1)
MAX_AHEAD = 16  # days of forecast the endpoint serves
# The forecast endpoint refused dates before today minus 93 days on 2026-10-14. Keep a margin.
MAX_BACK = 90


def check_date(date):
    d = Date.fromisoformat(date)
    if d < FIRST_DAY or d > Date.today() + timedelta(days=MAX_AHEAD):
        raise ValueError(f"{date} is out of range: use a date from {FIRST_DAY} to {MAX_AHEAD} days from today")
    return d


def endpoint(date, today=None):
    """URL and source label for a date."""
    today = today or Date.today()
    if check_date(date) < today - timedelta(days=MAX_BACK):
        return ARCHIVE_URL, "Open-Meteo archive (ERA5)"
    return URL, "Open-Meteo forecast"


def parse(resp, date, fetched=None, label="Open-Meteo forecast"):
    """Turn an Open-Meteo hourly response into weather.json rows for hours 5 to 20."""
    h = resp["hourly"]
    rows = []
    # Open-Meteo radiation is the mean over the hour before each stamp. It is used as is.
    for i, stamp in enumerate(h["time"]):
        day, clock = stamp.split("T")
        hour = int(clock[:2])
        if day == date and 5 <= hour <= 20:
            rows.append({"hour": hour, **{ours: h[theirs][i] for theirs, ours in FIELDS.items()}})
    if len(rows) != 16 or any(v is None for r in rows for v in r.values()):
        raise ValueError(f"Open-Meteo returned incomplete hourly data for {date}")
    fetched = fetched or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {"date": date, "tz": "+04:00", "hourly": rows, "source": f"{label}, fetched {fetched}"}


def fetch(date, lat=LAT, lon=LON):
    url, label = endpoint(date)
    params = {"latitude": lat, "longitude": lon, "hourly": ",".join(FIELDS), "wind_speed_unit": "ms",
              "timezone": "Asia/Dubai", "start_date": date, "end_date": date}
    r = httpx.get(url, params=params, timeout=20)
    r.raise_for_status()
    return parse(r.json(), date, label=label)
