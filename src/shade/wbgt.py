"""
Hourly weather to 15-minute slots, and outdoor WBGT from weather and shade.
"""
import json

import numpy as np

N_SLOTS = 60


def _hour(row):
    v = row.get("hour", row.get("time"))
    if isinstance(v, str):
        h, m = v.split(":")[:2]
        return int(h) + int(m) / 60
    return float(v)


def load_weather(path):
    """Read hourly rows (ta_c, rh_pct, wind_ms, ghi_wm2) and interpolate to slot midpoints."""
    data = json.loads(open(path, encoding="utf-8").read())
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    rows = sorted(rows, key=_hour)
    hours = [_hour(r) for r in rows]
    mids = [5 + (15 * s + 7.5) / 60 for s in range(N_SLOTS)]
    col = lambda k: np.interp(mids, hours, [r[k] for r in rows])
    ta, rh, wind, ghi = col("ta_c"), col("rh_pct"), col("wind_ms"), col("ghi_wm2")
    return [{"slot": s, "ta": round(float(ta[s]), 1), "rh": int(round(rh[s])),
             "wind": round(float(wind[s]), 1), "ghi": int(round(ghi[s]))} for s in range(N_SLOTS)]


def wbgt(ta, rh, sr_kw, ws):
    # Ono M., Tonouchi M. (2014) Estimation of wet-bulb globe temperature using generally
    # measured meteorological indices. Jpn J Biometeorol 50(4):147-157. Outdoor regression.
    return (0.735 * ta + 0.0374 * rh + 0.00292 * ta * rh + 7.619 * sr_kw
            - 4.557 * sr_kw ** 2 - 0.0572 * ws - 4.064)


def wbgt_at(w, f):
    """WBGT for one weather slot w at shade fraction f."""
    ghi = w["ghi"] / 1000
    # Diffuse sky light still reaches shade, taken as 15 percent of global radiation.
    sr = ghi * (1 - f) + 0.15 * ghi * f
    return round(wbgt(w["ta"], w["rh"], sr, w["wind"]), 1)


def wbgt_table(shade_fractions, weather):
    """shade_fractions[t][s] -> wbgt[t][s] in degrees C."""
    return [[wbgt_at(weather[s], f[s]) for s in range(N_SLOTS)] for f in shade_fractions]
