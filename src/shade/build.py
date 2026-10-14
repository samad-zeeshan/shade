"""
Run sun, shadow, heat and solver steps offline and write web/data.json.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, mapping, shape

from shade import scenario, weather as live
from shade.limits import WORK_MIN, load
from shade.phs import run_table
from shade.shadow import shade_fraction, slot_shadow
from shade.solve import metrics, solve
from shade.sun import LAT, LON, N_SLOTS, sun_table
from shade.wbgt import load_weather, wbgt_rest, wbgt_table

ROOT = Path(__file__).resolve().parents[2]
SHIFT_END = 48
BAN = (30, 39)
LABELS = {
    "ban_only": "Blanket ban",
    "sun_blind": "Heat limits, one site temperature",
    "shade_aware": "Heat limits, per-spot shade",
}
SOURCES = [
    {"key": "liljegren2008", "short": "Liljegren WBGT model",
     "citation": "Liljegren JC, Carhart RA, Lawday P, Tschopp S, Sharp R (2008). Modeling the wet bulb globe "
                 "temperature using standard meteorological measurements. Journal of Occupational and "
                 "Environmental Hygiene 5(10):645-655."},
    {"key": "brimicombe2022", "short": "thermofeel library",
     "citation": "Brimicombe C, Di Napoli C, Quintino T, Pappenberger F, Cornforth R, Cloke HL (2022). "
                 "thermofeel: a python thermal comfort indices library. SoftwareX 18:101005."},
    {"key": "niosh2016", "short": "NIOSH heat exposure limit",
     "citation": "NIOSH (2016). Criteria for a recommended standard: occupational exposure to heat and hot "
                 "environments. DHHS (NIOSH) Publication 2016-106, chapter 8, page 125."},
    {"key": "garzon2017", "short": "Validation of WBGT limits",
     "citation": "Garzon-Villalba XP, Wu Y, Ashley CD, Bernard TE (2017). Ability to discriminate between "
                 "sustainable and unsustainable heat stress exposures, part 1: WBGT exposure limits. Annals of "
                 "Work Exposures and Health 61(6):611-620."},
    {"key": "malchaire2001", "short": "Predicted heat strain model",
     "citation": "Malchaire J, Piette A, Kampmann B, Mehnert P, Gebhardt H, Havenith G, den Hartog E, Holmer I, "
                 "Parsons K, Alfano G, Griefahn B (2001). Development and validation of the predicted heat strain "
                 "model. Annals of Occupational Hygiene 45(2):123-135."},
]
DEFAULT_SOURCE = "Typical clear July day, hand written"
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
    raw = json.loads(Path(weather_path).read_text(encoding="utf-8"))
    date = raw.get("date", "2026-07-15")
    sun = sun_table(date=date)
    weather = load_weather(weather_path)
    rest = wbgt_rest(weather, sun)
    for w, r in zip(weather, rest):
        w["wbgt_rest"] = r
    points = [Point(TO_M(t["lon"], t["lat"])) for t in tasks]

    shadows, shade = [], [[0.0] * N_SLOTS for _ in tasks]
    for s, p in enumerate(sun):
        union, night = slot_shadow(footprints, p["azimuth"], p["elevation"])
        shadows.append({"slot": s, "night": night, "geometry": to_geojson(union)})
        for t, pt in enumerate(points):
            shade[t][s] = shade_fraction((pt.x, pt.y), union, night=night)

    wbgt, tr = wbgt_table(shade, weather, sun)
    loads = [[load(wbgt[t][s], rest[s], task["cls"]) for s in range(N_SLOTS)] for t, task in enumerate(tasks)]
    run_min, caps, clipped = run_table(tasks, weather, tr)
    blind_wbgt, blind_tr = wbgt_table([[0.0] * N_SLOTS for _ in tasks], weather, sun)
    blind = [[load(blind_wbgt[t][s], rest[s], task["cls"]) for s in range(N_SLOTS)] for t, task in enumerate(tasks)]
    _, blind_caps, _ = run_table(tasks, weather, blind_tr)
    print(f"PHS inputs clipped in {clipped} of {len(tasks) * N_SLOTS} cells")

    ban = set(range(BAN[0], BAN[1] + 1))
    scenarios = {}
    for key, heat, cap in (("ban_only", None, None), ("sun_blind", blind, blind_caps),
                           ("shade_aware", loads, caps)):
        r = solve(tasks, workers, heat, ban, N_SLOTS, SHIFT_END, time_limit, cap)
        print(f"{key}: {r['status']} objective={r['objective']} bound={r.get('bound')} "
              f"x={r.get('n_x')} wall={r['wall_s']:.1f}s")
        if r["assign"] is None:
            raise SystemExit(f"{key} found no schedule: {r['status']}")
        m = metrics(r["assign"], tasks, loads, wbgt, shade, SHIFT_END, caps)
        print("  ", m)
        scenarios[key] = {"label": LABELS[key], "metrics": m, "assign": r["assign"]}

    data = {
        "meta": {"site": "Plot 7 podium", "city": "Dubai", "date": date, "tz": "+04:00",
                 "center": [LON, LAT], "slot_minutes": 15, "first_slot": "05:00",
                 "shift_end_slot": SHIFT_END, "ban_slots": list(BAN), "n_slots": N_SLOTS,
                 "weather_source": raw.get("source", DEFAULT_SOURCE), "sources": SOURCES},
        "weather": weather,
        "sun": sun,
        "buildings": fc,
        "shadows": shadows,
        "tasks": [{**{k: t[k] for k in ("id", "name", "lon", "lat", "cls", "crew", "slots", "trade", "after")},
                   "shade": shade[i], "wbgt": wbgt[i], "load": loads[i],
                   "work_min": [WORK_MIN[v] for v in loads[i]], "run_min": run_min[i]}
                  for i, t in enumerate(tasks)],
        "workers": [{k: w[k] for k in ("id", "name", "trades")} for w in workers],
        "scenarios": scenarios,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {out} ({Path(out).stat().st_size / 1e6:.2f} MB)")
    return data


def main():
    ap = argparse.ArgumentParser(description="Build web/data.json.")
    ap.add_argument("--live", metavar="YYYY-MM-DD", help="fetch this day's forecast from Open-Meteo")
    args = ap.parse_args()
    if args.live:
        path = ROOT / "data" / "weather.live.json"
        path.write_text(json.dumps(live.fetch(args.live), indent=1), encoding="utf-8")
        build(weather_path=path)
    else:
        build()


if __name__ == "__main__":
    main()
