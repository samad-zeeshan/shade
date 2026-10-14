"""
Write a seeded mock of web/data.json so the frontend can be built before the real solver output exists.

Same schema as SPEC.md. The physics is rough on purpose and the schedules come from a greedy filler, not CP-SAT.
"""

import json
import math
import random
import sys
from pathlib import Path

LAT0, LON0 = 25.1860, 55.2650
N = 60
SHIFT_END = 48
BAN = range(30, 40)
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(LAT0))

LIMITS = {  # thresholds for 100, 75, 50, 25 percent work
    "light": [31.0, 31.5, 32.0, 32.5],
    "moderate": [28.0, 29.0, 30.0, 31.0],
    "heavy": [26.0, 27.5, 29.0, 30.0],
    "very_heavy": [25.0, 26.0, 27.5, 29.0],
}
LOADS = [12, 16, 24, 48]

# Hourly anchors 05:00..20:00 from the spec's weather shape.
TA = [32, 33, 34, 35.5, 37, 39, 40.5, 41.5, 42, 42.6, 43, 42, 41, 40, 38, 36]
RH = [62, 58, 54, 49, 44, 40, 36, 33, 31, 29, 28, 32, 36, 39, 42, 45]
WS = [2.5, 2.6, 2.8, 3.0, 3.3, 3.6, 4.0, 4.4, 4.8, 5.0, 4.9, 4.4, 3.8, 3.2, 2.8, 2.5]


def interp(arr, hour):
    i = min(int(hour), len(arr) - 2)
    f = hour - i
    return arr[i] * (1 - f) + arr[i + 1] * f


def ghi(local_h):
    # Bell between 05:50 and 19:15, 950 at 12:00 peak.
    if local_h < 5.85 or local_h > 19.25:
        return 0.0
    x = (local_h - 12.55) / 6.7
    return max(0.0, 950 * math.cos(x * math.pi / 2) ** 1.4)


def sun(local_h):
    dec = math.radians(21.5)
    lat = math.radians(LAT0)
    ha = math.radians((local_h - 12.33) * 15)
    el = math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha))
    az = math.atan2(math.sin(ha), math.cos(ha) * math.sin(lat) - math.tan(dec) * math.cos(lat))
    return (math.degrees(az) + 180) % 360, math.degrees(el)


def to_ll(x, y):
    return [round(LON0 + x / M_LON, 6), round(LAT0 + y / M_LAT, 6)]


def hull(pts):
    pts = sorted(set(pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def inside(pt, poly):
    x, y = pt
    hit = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def load_for(wbgt, cls):
    for thr, ld in zip(LIMITS[cls], LOADS):
        if wbgt <= thr:
            return ld
    return None


def main():
    rnd = random.Random(7)
    out = Path(__file__).resolve().parent.parent / "web" / "data.json"
    if out.exists() and "--force" not in sys.argv:
        print(f"{out} exists, not overwriting (pass --force)")
        return

    # Towers east and west of an open plot, boxes in metres (x0, y0, x1, y1, h).
    towers = [
        (-150, -40, -110, 10, 118), (-160, 30, -125, 70, 84), (-140, -110, -105, -75, 46),
        (105, -30, 140, 15, 102), (115, 40, 150, 80, 66), (100, -100, 135, -70, 40),
    ]
    names = ["Canal Tower", "Bay Square 4", "Plot 5 block", "Marasi Heights", "Executive Tower K", "Car park B"]
    buildings = {"type": "FeatureCollection", "features": []}
    for (x0, y0, x1, y1, h), nm in zip(towers, names):
        ring = [to_ll(x0, y0), to_ll(x1, y0), to_ll(x1, y1), to_ll(x0, y1), to_ll(x0, y0)]
        buildings["features"].append({"type": "Feature", "properties": {"height": float(h), "name": nm},
                                      "geometry": {"type": "Polygon", "coordinates": [ring]}})

    weather, suns, shadows, shadow_m = [], [], [], []
    for s in range(N):
        h = 5 + (s * 15 + 7.5) / 60
        az, el = sun(h)
        weather.append({"slot": s, "ta": round(interp(TA, h - 5), 1), "rh": round(interp(RH, h - 5)),
                        "wind": round(interp(WS, h - 5), 1), "ghi": round(ghi(h))})
        suns.append({"slot": s, "azimuth": round(az, 1), "elevation": round(el, 1)})
        if el <= 1:
            shadows.append({"slot": s, "night": True, "geometry": None})
            shadow_m.append(None)
            continue
        polys = []
        for x0, y0, x1, y1, ht in towers:
            l = min(600.0, ht / math.tan(math.radians(el)))
            dx, dy = -l * math.sin(math.radians(az)), -l * math.cos(math.radians(az))
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            polys.append(hull(corners + [(cx + dx, cy + dy) for cx, cy in corners]))
        shadow_m.append(polys)
        geom = {"type": "MultiPolygon",
                "coordinates": [[[to_ll(*p) for p in poly + [poly[0]]]] for poly in polys]}
        shadows.append({"slot": s, "night": False, "geometry": geom})

    task_defs = [
        ("Tie rebar, grid A", "very_heavy", 3, 14, "steel", []),
        ("Tie rebar, grid B", "heavy", 3, 12, "steel", []),
        ("Fix column cages", "heavy", 3, 12, "steel", ["T01"]),
        ("Erect wall formwork", "very_heavy", 3, 14, "concrete", []),
        ("Pour slab strip 1", "moderate", 2, 10, "concrete", ["T04"]),
        ("Strip formwork, core", "moderate", 2, 8, "concrete", []),
        ("Place starter bars", "moderate", 2, 10, "steel", []),
        ("Block wall, east side", "moderate", 2, 12, "general", []),
        ("Backfill, west trench", "moderate", 2, 10, "general", []),
        ("Waterproof podium edge", "moderate", 2, 8, "general", ["T09"]),
        ("Survey setting out", "light", 1, 6, "general", []),
        ("Pull cable, zone 2", "light", 2, 8, "electrical", []),
        ("Test earthing pits", "light", 1, 4, "electrical", []),
        ("Inspect rebar cover", "light", 1, 4, "steel", []),
        ("Fit conduit sleeves", "light", 2, 6, "electrical", []),
        ("Snag list, level 1", "light", 1, 5, "concrete", []),
    ]
    tasks = []
    for i, (nm, cls, crew, slots, trade, after) in enumerate(task_defs):
        x, y = rnd.uniform(-90, 90), rnd.uniform(-75, 75)
        shade, wbgt, load = [], [], []
        for s in range(N):
            polys = shadow_m[s]
            if polys is None:
                f = 1.0
            else:
                pts = [(x, y)] + [(x + 6 * math.cos(k * math.pi / 4), y + 6 * math.sin(k * math.pi / 4)) for k in range(8)]
                f = sum(any(inside(p, poly) for poly in polys) for p in pts) / len(pts)
            w = weather[s]
            sr = w["ghi"] * (1 - f) + 0.15 * w["ghi"] * f
            sr /= 1000
            ta, rh, ws = w["ta"], w["rh"], w["wind"]
            v = 0.735 * ta + 0.0374 * rh + 0.00292 * ta * rh + 7.619 * sr - 4.557 * sr * sr - 0.0572 * ws - 4.064
            shade.append(round(f, 2))
            wbgt.append(round(v, 1))
            load.append(load_for(v, cls))
        lon, lat = to_ll(x, y)
        tasks.append({"id": f"T{i + 1:02d}", "name": nm, "lon": lon, "lat": lat, "cls": cls, "crew": crew,
                      "slots": slots, "trade": trade, "after": after, "shade": shade, "wbgt": wbgt, "load": load})

    roster = [("Rafiq", "steel"), ("Imran", "steel"), ("Sanjay", "steel"), ("Khalid", "steel"), ("Anil", "steel"),
              ("Bilal", "concrete"), ("Omar", "concrete"), ("Suresh", "concrete"), ("Yousef", "concrete"),
              ("Tariq", "general"), ("Ravi", "general"), ("Hamza", "general"),
              ("Nabil", "electrical"), ("Deepak", "electrical")]
    workers = [{"id": f"W{i + 1:02d}", "name": n, "trades": [t]} for i, (n, t) in enumerate(roster)]

    scen = {
        "ban_only": ("Blanket ban", None),
        "sun_blind": ("Heat limits, one site temperature", "blind"),
        "shade_aware": ("Heat limits, per-spot shade", "true"),
    }
    by_id = {t["id"]: t for t in tasks}
    scenarios = {}
    for key, (label, mode) in scen.items():
        assign = [[None] * N for _ in workers]
        left = {t["id"]: t["slots"] for t in tasks}
        done_at = {}

        def plan_load(t, s):
            if mode is None:
                return 0
            if mode == "blind":
                w = weather[s]
                sr = w["ghi"] / 1000
                ta, rh, ws = w["ta"], w["rh"], w["wind"]
                v = 0.735 * ta + 0.0374 * rh + 0.00292 * ta * rh + 7.619 * sr - 4.557 * sr * sr - 0.0572 * ws - 4.064
                return load_for(v, t["cls"])
            return t["load"][s]

        for s in range(N):
            if s in BAN:
                continue
            busy = set()
            for t in sorted(tasks, key=lambda t: -t["crew"]):
                if left[t["id"]] == 0 or any(done_at.get(a, N + 1) > s for a in t["after"]):
                    continue
                ld = plan_load(t, s)
                if ld is None:
                    continue
                ok = []
                for wi, w in enumerate(workers):
                    if wi in busy or t["trade"] not in w["trades"]:
                        continue
                    past = sum(plan_load(by_id[a], s2) or 0 for s2 in range(max(0, s - 3), s)
                               if (a := assign[wi][s2]))
                    if past + ld <= 48:
                        ok.append(wi)
                if len(ok) < t["crew"]:
                    continue
                for wi in ok[:t["crew"]]:
                    assign[wi][s] = t["id"]
                    busy.add(wi)
                left[t["id"]] -= 1
                if left[t["id"]] == 0:
                    done_at[t["id"]] = s + 1

        # Post-hoc metrics with the true load, same rules as the spec.
        worked = [(wi, s) for wi in range(len(workers)) for s in range(N) if assign[wi][s]]
        viol = set()
        for wi in range(len(workers)):
            for s0 in range(N - 3):
                tot = 0
                for s in range(s0, s0 + 4):
                    tid = assign[wi][s]
                    if tid:
                        ld = by_id[tid]["load"][s]
                        tot += 49 if ld is None else ld
                if tot > 48:
                    viol.update((wi, s) for s in range(s0, s0 + 4) if assign[wi][s])
        metrics = {
            "overtime_hours": sum(1 for _, s in worked if s >= SHIFT_END) / 4,
            "unscheduled_hours": sum(left[t["id"]] * t["crew"] for t in tasks) / 4,
            "violation_hours": len(viol) / 4,
            "tasks_done_by_17": sum(1 for t in tasks if left[t["id"]] == 0 and done_at[t["id"]] <= SHIFT_END),
            "peak_wbgt_worked": max(by_id[assign[wi][s]]["wbgt"][s] for wi, s in worked),
            "mean_shade_worked": round(sum(by_id[assign[wi][s]]["shade"][s] for wi, s in worked) / len(worked), 3),
        }
        scenarios[key] = {"label": label, "metrics": metrics, "assign": assign}
        print(key, metrics)

    data = {
        "meta": {"site": "Plot 7 podium", "city": "Dubai", "date": "2026-07-15", "tz": "+04:00",
                 "center": [LON0, LAT0], "slot_minutes": 15, "first_slot": "05:00",
                 "shift_end_slot": SHIFT_END, "ban_slots": [30, 39], "n_slots": N},
        "weather": weather, "sun": suns, "buildings": buildings, "shadows": shadows,
        "tasks": tasks, "workers": workers, "scenarios": scenarios,
    }
    out.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
