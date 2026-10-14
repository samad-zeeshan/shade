"""
Fetch building footprints around a site from Overpass and save data/buildings/<site id>.geojson.

Run once with network access: uv run python -m shade.osm --site sites/plot7.json
"""
import argparse
import json
import re
from pathlib import Path

import httpx
from pyproj import Transformer
from shapely.geometry import Polygon

from shade.scenario import load_site

SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "buildings"
MIN_AREA_M2 = 20.0

QUERY = """[out:json][timeout:60];
(way["building"]({s},{w},{n},{e});
 relation["building"]({s},{w},{n},{e}););
out geom tags;"""


def fetch(site: dict) -> dict:
    (lon, lat), (dlon, dlat) = site["center"], site["bbox_half_deg"]
    q = QUERY.format(s=lat - dlat, n=lat + dlat, w=lon - dlon, e=lon + dlon)
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
    ap = argparse.ArgumentParser(description="Download building footprints for one site.")
    ap.add_argument("--site", default="sites/plot7.json")
    site = load_site(ap.parse_args().site)
    out = OUT_DIR / f"{site['id']}.geojson"
    to_m = Transformer.from_crs(4326, 32640, always_xy=True).transform
    features = []
    for el in fetch(site)["elements"]:
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
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    hs = [f["properties"]["height"] for f in features]
    print(f"{len(features)} buildings, max height {max(hs)} m -> {out}")


if __name__ == "__main__":
    main()
