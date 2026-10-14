"""
Run sun, shadow, heat and solver steps offline for every site and weather day.

Writes one web/runs/<site>-<date>.json per run and the list of runs in web/runs.json.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Point, Polygon, mapping, shape

from shade import scenario, weather as live
from shade.limits import M, WORK_MIN, load
from shade.phs import run_table
from shade.shadow import shade_fraction, slot_shadow
from shade.solve import metrics, solve
from shade.sun import N_SLOTS, sun_table
from shade.wbgt import load_weather, wbgt_rest, wbgt_table

ROOT = Path(__file__).resolve().parents[2]
WEATHER = ROOT / "data" / "weather"
RUNS = ROOT / "web" / "runs"
GRID_STEP_M = 6
GRID_MAX_POINTS = 500
GRID_BUFFER_M = 25
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


def grid_points(area, step=GRID_STEP_M, cap=GRID_MAX_POINTS):
    """Cell centres every step metres inside area. The step grows by 1 m until at most cap points remain."""
    x0, y0, x1, y1 = area.bounds
    while True:
        xs, ys = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
        xs, ys = xs.ravel(), ys.ravel()
        keep = shapely.contains_xy(area, xs, ys)
        if keep.sum() <= cap:
            return step, xs[keep], ys[keep]
        step += 1


def allowance_grid(area, unions, weather, sun, rest):
    """Work minutes per hour for every grid point, slot and work class, one digit (minutes / 15) per slot."""
    step, xs, ys = grid_points(area)
    # Clip each slot's shadow to the plot first, so each disc test touches a small polygon, not the whole district.
    clip = shapely.box(*area.buffer(6.0).bounds)
    local = [(None if u is None else u.intersection(clip), night) for u, night in unions]
    shade = [[shade_fraction((x, y), u, night=night) for u, night in local] for x, y in zip(xs, ys)]
    wbgt, _ = wbgt_table(shade, weather, sun)
    lon, lat = TO_DEG(xs, ys)
    return {
        "step_m": step,
        "points": [[round(float(a), 6), round(float(b), 6)] for a, b in zip(lon, lat)],
        "classes": list(M),
        "work": {c: ["".join(str(WORK_MIN[load(v, r, c)] // 15) for v, r in zip(row, rest)) for row in wbgt]
                 for c in M},
    }


def solver_info(r):
    gap = 0.0 if r["status"] == "OPTIMAL" else round(100 * (r["objective"] - r["bound"]) / max(r["objective"], 1), 1)
    return {"status": r["status"], "objective": r["objective"], "bound": r.get("bound"), "gap_pct": gap}


def build(site, weather_path, out=None, time_limit=60.0):
    """Build one run for a site and one weather file. out defaults to web/runs/<site>-<date>.json."""
    fc, buildings = load_buildings(ROOT / "data" / "buildings" / f"{site['id']}.geojson")
    footprints = list(polygons(buildings))
    tasks, workers = site["tasks"], site["workers"]
    lon, lat = site["center"]
    raw = json.loads(Path(weather_path).read_text(encoding="utf-8"))
    date = raw.get("date", Path(weather_path).stem)
    run_id = f"{site['id']}-{date}"
    sun = sun_table(lat, lon, date=date)
    weather = load_weather(weather_path)
    rest = wbgt_rest(weather, sun)
    for w, r in zip(weather, rest):
        w["wbgt_rest"] = r
    points = [Point(TO_M(t["lon"], t["lat"])) for t in tasks]

    shadows, unions, shade = [], [], [[0.0] * N_SLOTS for _ in tasks]
    for s, p in enumerate(sun):
        union, night = slot_shadow(footprints, p["azimuth"], p["elevation"])
        unions.append((union, night))
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

    shift_end, (ban0, ban1) = site["shift_end_slot"], site["ban_slots"]
    ban = set(range(ban0, ban1 + 1))
    scenarios = {}
    for key, heat, cap in (("ban_only", None, None), ("sun_blind", blind, blind_caps),
                           ("shade_aware", loads, caps)):
        r = solve(tasks, workers, heat, ban, N_SLOTS, shift_end, time_limit, cap)
        print(f"{key}: {r['status']} objective={r['objective']} bound={r.get('bound')} "
              f"x={r.get('n_x')} wall={r['wall_s']:.1f}s")
        if r["assign"] is None:
            raise SystemExit(f"{key} found no schedule: {r['status']}")
        m = metrics(r["assign"], tasks, loads, wbgt, shade, shift_end, caps)
        print("  ", m)
        scenarios[key] = {"label": LABELS[key], "metrics": m, "assign": r["assign"], "solver": solver_info(r)}

    if "plot" in site:
        area = transform(TO_M, Polygon(site["plot"]))
    else:
        area = MultiPoint([(p.x, p.y) for p in points]).convex_hull.buffer(GRID_BUFFER_M)
    # Points inside a footprint are roofs, not ground, so they get no allowance.
    area = area.difference(shapely.union_all([g for g, _ in footprints]))
    grid = allowance_grid(area, unions, weather, sun, rest)

    data = {
        "meta": {"site": site["name"], "city": site["city"], "site_id": site["id"], "run_id": run_id,
                 "date": date, "tz": "+04:00", "center": [lon, lat], "slot_minutes": 15, "first_slot": "05:00",
                 "shift_end_slot": shift_end, "ban_slots": [ban0, ban1], "n_slots": N_SLOTS,
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
        "grid": grid,
    }
    out = Path(out) if out else RUNS / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    grid_kb = len(json.dumps(grid, separators=(",", ":"))) / 1e3
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB, grid {len(grid['points'])} points "
          f"at {grid['step_m']} m, {grid_kb:.0f} KB)")
    return data


def summary(data):
    """One web/runs.json entry for a built run."""
    meta, sc = data["meta"], data["scenarios"]
    extra = lambda k: sc[k]["metrics"]["overtime_hours"] + sc[k]["metrics"]["unscheduled_hours"]
    morning = data["weather"][8:24]  # slots from 07:00 to 11:00
    return {"id": meta["run_id"], "file": f"runs/{meta['run_id']}.json", "site": meta["site"],
            "city": meta["city"], "date": meta["date"], "source": meta["weather_source"],
            "morning_rh": round(sum(w["rh"] for w in morning) / len(morning)),
            "morning_ta": round(sum(w["ta"] for w in morning) / len(morning), 1),
            "blind_extra_h": extra("sun_blind"), "shade_extra_h": extra("shade_aware"),
            "ban_over_h": sc["ban_only"]["metrics"]["violation_hours"]}


def manifest(entries):
    """Runs sorted by city then date. The default run is the one where shade saves the most hours."""
    runs = sorted(entries, key=lambda e: (e["city"], e["date"], e["id"]))
    best = max(runs, key=lambda e: e["blind_extra_h"] - e["shade_extra_h"], default=None)
    return {"default": best and best["id"], "runs": runs}


def main():
    ap = argparse.ArgumentParser(description="Build every site in sites/ against each weather file in data/weather/<site>/.")
    ap.add_argument("--live", metavar="YYYY-MM-DD", help="fetch this day from Open-Meteo for --site, then build it")
    ap.add_argument("--site", default="sites/plot7.json", help="site file for --live")
    ap.add_argument("--only", metavar="SITE/YYYY-MM-DD", help="rebuild one run and keep the other run files")
    ap.add_argument("--time-limit", type=float, default=60.0, help="solver seconds per scenario")
    args = ap.parse_args()
    only = args.only
    if args.live:
        site = scenario.load_site(args.site)
        lon, lat = site["center"]
        path = WEATHER / site["id"] / f"{args.live}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(live.fetch(args.live, lat, lon), indent=1), encoding="utf-8")
        only = f"{site['id']}/{args.live}"
    entries, built = [], 0
    for f in sorted((ROOT / "sites").glob("*.json")):
        site = scenario.load_site(f)
        for w in sorted((WEATHER / site["id"]).glob("*.json")):
            run_file = RUNS / f"{site['id']}-{w.stem}.json"
            if only in (None, f"{site['id']}/{w.stem}"):
                data, built = build(site, w, run_file, args.time_limit), built + 1
            elif run_file.exists():
                data = json.loads(run_file.read_text(encoding="utf-8"))
            else:
                continue
            entries.append(summary(data))
    if not built:
        raise SystemExit(f"no weather file matches {only}")
    out = ROOT / "web" / "runs.json"
    out.write_text(json.dumps(manifest(entries), indent=1), encoding="utf-8")
    print(f"wrote {out} with {len(entries)} runs")


if __name__ == "__main__":
    main()
