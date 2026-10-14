"""
Run sun, shadow, heat and solver steps offline and write web/data.json.
"""
import json
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, mapping, shape

from shade import scenario
from shade.limits import load
from shade.shadow import shade_fraction, slot_shadow
from shade.solve import metrics, solve
from shade.sun import LAT, LON, N_SLOTS, sun_table
from shade.wbgt import load_weather, wbgt_table

ROOT = Path(__file__).resolve().parents[2]
SHIFT_END = 48
BAN = (30, 39)
LABELS = {
    "ban_only": "Blanket ban",
    "sun_blind": "Heat limits, one site temperature",
    "shade_aware": "Heat limits, per-spot shade",
}
TO_M = Transformer.from_crs(4326, 32640, always_xy=True).transform
TO_DEG = Transformer.from_crs(32640, 4326, always_xy=True).transform


def transform(fn, geom):
    return shapely.transform(geom, lambda c: np.column_stack(fn(c[:, 0], c[:, 1])))


def load_buildings(path):
    fc = json.loads(Path(path).read_text(encoding="utf-8"))
    return fc, [(transform(TO_M, shape(f["geometry"])), float(f["properties"]["height"])) for f in fc["features"]]


def polygons(buildings):
    """Split any MultiPolygon footprints so the shadow sweep sees single rings."""
    for g, h in buildings:
        for p in getattr(g, "geoms", [g]):
            yield p, h


def to_geojson(geom):
    if geom is None or geom.is_empty:
        return None
    g = shapely.transform(transform(TO_DEG, geom), lambda c: np.round(c, 6))
    polys = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]
    return mapping(MultiPolygon(polys)) if polys else None


def build(buildings_path=ROOT / "data" / "buildings.geojson", weather_path=ROOT / "data" / "weather.json",
          out=ROOT / "web" / "data.json", time_limit=60.0):
    fc, buildings = load_buildings(buildings_path)
    footprints = list(polygons(buildings))
    tasks, workers = scenario.TASKS, scenario.WORKERS
    sun = sun_table()
    weather = load_weather(weather_path)
    points = [Point(TO_M(t["lon"], t["lat"])) for t in tasks]

    shadows, shade = [], [[0.0] * N_SLOTS for _ in tasks]
    for s, p in enumerate(sun):
        union, night = slot_shadow(footprints, p["azimuth"], p["elevation"])
        shadows.append({"slot": s, "night": night, "geometry": to_geojson(union)})
        for t, pt in enumerate(points):
            shade[t][s] = shade_fraction((pt.x, pt.y), union, night=night)

    wbgt = wbgt_table(shade, weather)
    loads = [[load(wbgt[t][s], task["cls"]) for s in range(N_SLOTS)] for t, task in enumerate(tasks)]
    blind_wbgt = wbgt_table([[0.0] * N_SLOTS for _ in tasks], weather)
    blind = [[load(blind_wbgt[t][s], task["cls"]) for s in range(N_SLOTS)] for t, task in enumerate(tasks)]

    ban = set(range(BAN[0], BAN[1] + 1))
    scenarios = {}
    for key, heat in (("ban_only", None), ("sun_blind", blind), ("shade_aware", loads)):
        r = solve(tasks, workers, heat, ban, N_SLOTS, SHIFT_END, time_limit)
        print(f"{key}: {r['status']} objective={r['objective']} bound={r.get('bound')} "
              f"x={r.get('n_x')} wall={r['wall_s']:.1f}s")
        if r["assign"] is None:
            raise SystemExit(f"{key} found no schedule: {r['status']}")
        m = metrics(r["assign"], tasks, loads, wbgt, shade, SHIFT_END)
        print("  ", m)
        scenarios[key] = {"label": LABELS[key], "metrics": m, "assign": r["assign"]}

    data = {
        "meta": {"site": "Plot 7 podium", "city": "Dubai", "date": "2026-07-15", "tz": "+04:00",
                 "center": [LON, LAT], "slot_minutes": 15, "first_slot": "05:00",
                 "shift_end_slot": SHIFT_END, "ban_slots": list(BAN), "n_slots": N_SLOTS,
                 "limits_source": "ACGIH TLV screening table, CCOHS reproduction",
                 "wbgt_source": "Ono and Tonouchi 2014 regression, coefficients unverified"},
        "weather": weather,
        "sun": sun,
        "buildings": fc,
        "shadows": shadows,
        "tasks": [{**{k: t[k] for k in ("id", "name", "lon", "lat", "cls", "crew", "slots", "trade", "after")},
                   "shade": shade[i], "wbgt": wbgt[i], "load": loads[i]} for i, t in enumerate(tasks)],
        "workers": [{k: w[k] for k in ("id", "name", "trades")} for w in workers],
        "scenarios": scenarios,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {out} ({Path(out).stat().st_size / 1e6:.2f} MB)")
    return data


if __name__ == "__main__":
    build()
