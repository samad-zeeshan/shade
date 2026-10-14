"""
Load site files from sites/ and check that task points sit in open ground.

Plot 7 was found by a grid search over the OSM footprints, see the README.
"""
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
MIN_CLEARANCE_M = 8.0


def load_site(site):
    """Read a site file. site is an id like "plot7" or a path to a JSON file."""
    path = Path(site) if str(site).endswith(".json") else ROOT / "sites" / f"{site}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# Plot 7 task points sit where tower shadows fall: five in morning shade (north-west corner
# and east edge), four in late-afternoon shade (south-west), the rest in sun all day.
# Heavy and moderate work goes in morning shade, because after 10:00 the heat table
# allows only light work even in shade. Light work goes in the afternoon shade spots.
# Half the crew holds a second trade, so one trade running short does not stall the site.
SITE = load_site("plot7")
PLOT_CENTER = tuple(SITE["plot_center"])  # (lon, lat)
TASKS, WORKERS = SITE["tasks"], SITE["workers"]


def assert_tasks_in_open_ground(buildings_geojson_path, tasks=TASKS):
    """Raise if any task point is within 8 m of a building footprint."""
    to_m = Transformer.from_crs(4326, 32640, always_xy=True).transform
    feats = json.loads(Path(buildings_geojson_path).read_text())["features"]
    ground = unary_union([
        Polygon([to_m(*p) for p in f["geometry"]["coordinates"][0]]) for f in feats
    ])
    for t in tasks:
        d = ground.distance(Point(*to_m(t["lon"], t["lat"])))
        if d < MIN_CLEARANCE_M:
            raise AssertionError(f"{t['id']} is {d:.1f} m from a building, need {MIN_CLEARANCE_M} m")


if __name__ == "__main__":
    import sys
    site = load_site(sys.argv[1] if len(sys.argv) > 1 else "plot7")
    assert_tasks_in_open_ground(ROOT / "data" / "buildings" / f"{site['id']}.geojson", site["tasks"])
    print("ok, sum crew x slots =", sum(t["crew"] * t["slots"] for t in site["tasks"]))
