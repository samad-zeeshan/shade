"""
Solar position from the NOAA solar calculator equations.
"""
import math
from datetime import datetime, timedelta, timezone

LAT, LON = 25.1860, 55.2650
TZ = timezone(timedelta(hours=4))
DAY = datetime(2026, 7, 15, tzinfo=TZ)
N_SLOTS = 60


def sun_position(lat, lon, dt_utc):
    """Return (azimuth clockwise from north, elevation) in degrees."""
    doy = dt_utc.timetuple().tm_yday
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour * 60 + eqtime + 4 * lon  # true solar time in minutes, input is UTC
    ha = math.radians(tst / 4 - 180)
    phi = math.radians(lat)
    cos_zen = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    el = 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zen))))
    # atan2 form avoids the quadrant fix-ups of the arccos azimuth in the NOAA sheet.
    az = math.degrees(math.atan2(-math.sin(ha), math.tan(decl) * math.cos(phi) - math.sin(phi) * math.cos(ha)))
    return az % 360, el


def slot_time(s, day=DAY):
    """Local start time of slot s."""
    return day.replace(hour=5) + timedelta(minutes=15 * s)


def sun_table(lat=LAT, lon=LON, date=None):
    """Sun at each slot midpoint. date is an ISO day string, default the demo day."""
    day = datetime.fromisoformat(date).replace(tzinfo=TZ) if date else DAY
    out = []
    for s in range(N_SLOTS):
        mid = (slot_time(s, day) + timedelta(minutes=7.5)).astimezone(timezone.utc)
        az, el = sun_position(lat, lon, mid)
        out.append({"slot": s, "azimuth": round(az, 1), "elevation": round(el, 1)})
    return out
