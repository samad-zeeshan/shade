"""
Hourly weather to 15-minute slots, and outdoor WBGT and mean radiant temperature per spot.

WBGT is the Liljegren model as implemented in thermofeel.
"""
import json

import numpy as np
import thermofeel
from thermofeel import liljegren

N_SLOTS = 60
EXTRA = ("dir", "dif", "pressure")  # optional hourly fields, present in live weather


def _hour(row):
    v = row.get("hour", row.get("time"))
    if isinstance(v, str):
        h, m = v.split(":")[:2]
        return int(h) + int(m) / 60
    return float(v)


def load_weather(path):
    """Read hourly rows (ta_c, rh_pct, wind_ms, ghi_wm2) and interpolate to slot midpoints."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    rows = sorted(rows, key=_hour)
    hours = [_hour(r) for r in rows]
    mids = [5 + (15 * s + 7.5) / 60 for s in range(N_SLOTS)]
    col = lambda k: np.interp(mids, hours, [r[k] for r in rows])
    ta, rh, wind, ghi = col("ta_c"), col("rh_pct"), col("wind_ms"), col("ghi_wm2")
    out = [{"slot": s, "ta": round(float(ta[s]), 1), "rh": int(round(rh[s])),
            "wind": round(float(wind[s]), 1), "ghi": int(round(ghi[s]))} for s in range(N_SLOTS)]
    for k in EXTRA:
        if all(k in r for r in rows):
            for s, v in enumerate(col(k)):
                out[s][k] = round(float(v), 1)
    return out


def _inputs(f, weather, sun):
    """Liljegren inputs over all slots for one spot with shade fractions f."""
    f = np.asarray(f, dtype=float)
    ta = np.array([w["ta"] for w in weather], dtype=float)
    rh = np.array([w["rh"] for w in weather], dtype=float)
    va = np.array([w["wind"] for w in weather], dtype=float)
    pressure = np.array([w.get("pressure", 1010.0) for w in weather])
    ghi = np.array([w["ghi"] for w in weather], dtype=float)
    # Without measured splits, take 15 percent of global light as diffuse sky light, which still reaches shade.
    dif = np.array([w.get("dif", 0.15 * w["ghi"]) for w in weather], dtype=float)
    direct = np.array([w.get("dir", 0.85 * w["ghi"]) for w in weather], dtype=float)
    el = np.array([p["elevation"] for p in sun], dtype=float)
    night = el <= 1
    ssrd = np.where(night, 0.0, ghi * (1 - f) + dif * f)
    with np.errstate(divide="ignore", invalid="ignore"):
        fdir = np.where(ssrd > 0, np.clip(direct * (1 - f) / ssrd, 0, 1), 0.0)
    # A floor on cos(zenith) keeps the direct beam term finite when the sun sits on the horizon.
    cossza = np.maximum(np.sin(np.radians(el)), 0.05)
    return ta, rh, va, pressure, ssrd, fdir, cossza


def mean_radiant(ta, rh, va, pressure, ssrd, fdir, cossza):
    """Mean radiant temperature in C from the Liljegren globe temperature."""
    t2_k = ta + 273.15
    va10 = np.maximum(va, 0.62)  # same wind floor as thermofeel applies inside the WBGT call
    v2 = thermofeel.calculate_wind_speed_2m_liljegren(va10, cossza, ssrd)
    fdir = np.where(cossza < liljegren.CZA_MIN, 0.0, np.clip(fdir, 0, 0.9))
    tg = liljegren.solve_globe(t2_k, rh / 100, pressure, v2, ssrd, fdir, cossza)
    # ISO 7726 forced convection for a black globe (emissivity 0.95), sized to the 50.8 mm Liljegren globe.
    d = liljegren.D_GLOBE
    return ((tg + 273.15) ** 4 + 1.1e8 * v2 ** 0.6 * (tg - ta) / (0.95 * d ** 0.4)) ** 0.25 - 273.15


def wbgt_table(shade_fractions, weather, sun):
    """shade_fractions[t][s] -> (wbgt[t][s], tr[t][s]) in degrees C, one decimal."""
    wbgt, tr = [], []
    for f in shade_fractions:
        ta, rh, va, p, ssrd, fdir, cossza = _inputs(f, weather, sun)
        # Liljegren JC et al. (2008) J Occup Environ Hyg 5(10):645-655, via thermofeel (Brimicombe et al. 2022).
        k = thermofeel.calculate_wbgt_liljegren(ta + 273.15, rh, p, va, ssrd, fdir, cossza)
        wbgt.append([round(float(v), 1) for v in k - 273.15])
        tr.append([round(float(v), 1) for v in mean_radiant(ta, rh, va, p, ssrd, fdir, cossza)])
    return wbgt, tr


def wbgt_rest(weather, sun):
    """WBGT in full shade per slot. Workers rest in shade."""
    return wbgt_table([[1.0] * len(weather)], weather, sun)[0][0]
