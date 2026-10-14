"""
Fetch building footprints for the site from Overpass and save data/buildings.geojson.

Run once with network access: uv run python -m shade.osm
"""
import json
import re
from pathlib import Path

import httpx
from pyproj import Transformer
from shapely.geometry import Polygon

CENTER_LAT, CENTER_LON = 25.1860, 55.2650
DLAT, DLON = 0.0035, 0.0040
SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OUT = Path(__file__).resolve().parents[2] / "data" / "buildings.geojson"
MIN_AREA_M2 = 20.0

QUERY = """[out:json][timeout:60];
(way["building"]({s},{w},{n},{e});
 relation["building"]({s},{w},{n},{e}););
out geom tags;"""


def fetch() -> dict:
    q = QUERY.format(s=CENTER_LAT - DLAT, n=CENTER_LAT + DLAT, w=CENTER_LON - DLON, e=CENTER_LON + DLON)
    last = None
    for url in SERVERS:
        try:
            r = httpx.post(url, data={"data": q}, headers={"User-Agent": "shade-demo/0.1"}, timeout=90)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            print(f"{url} failed: {exc}")
    raise RuntimeError(f"all Overpass servers failed: {last}")


def height_of(tags: dict) -> float:
    # Tags like "84 m" or "84.5" both occur. Fall back to levels, then a default.
    for key, scale in (("height", 1.0), ("building:levels", 3.2)):
        m = re.match(r"\s*([\d.]+)", tags.get(key, ""))
        if m:
            try:
                return round(float(m.group(1)) * scale, 1)
            except ValueError:
                pass
    return 12.0


def ring_of(geometry: list[dict]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in geometry]


def main() -> None:
    to_m = Transformer.from_crs(4326, 32640, always_xy=True).transform
    features = []
    for el in fetch()["elements"]:
        if el["type"] == "way":
            ring = ring_of(el.get("geometry", []))
        else:
            # shortcut: outer ring only, first outer member, inner courtyards ignored.
            outers = [m for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
            ring = ring_of(outers[0]["geometry"]) if outers else []
        if len(ring) < 4:
            continue
        poly = Polygon(ring)
        if not poly.is_valid or Polygon([to_m(*pt) for pt in ring]).area < MIN_AREA_M2:
            continue
        tags = el.get("tags", {})
        features.append({
            "type": "Feature",
            "properties": {"height": height_of(tags), "name": tags.get("name", "")},
            "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in poly.exterior.coords]]},
        })
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    hs = [f["properties"]["height"] for f in features]
    print(f"{len(features)} buildings, max height {max(hs)} m -> {OUT}")


if __name__ == "__main__":
    main()
