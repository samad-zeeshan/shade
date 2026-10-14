"""
Site definition for the demo: Plot 7 podium tasks, workers, and the plot location.

The plot was found by a grid search over the OSM footprints, see the README.
"""
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

PLOT_CENTER = (55.263988, 25.187433)  # (lon, lat)
MIN_CLEARANCE_M = 8.0


def _t(id, name, lat, lon, cls, crew, slots, trade, after=()):
    return dict(id=id, name=name, lat=lat, lon=lon, cls=cls, crew=crew, slots=slots,
                trade=trade, after=list(after))


# Points sit where tower shadows fall: five in morning shade (north-west corner and east
# edge), four in late-afternoon shade (south-west), the rest in sun all day.
# Heavy and moderate work goes in morning shade, because after 10:00 the heat table
# allows only light work even in shade. Light work goes in the afternoon shade spots.
TASKS = [
    _t("T01", "Survey podium levels", 25.187067, 55.263596, "light", 2, 6, "general"),
    _t("T02", "Place column cages", 25.187801, 55.264578, "moderate", 2, 6, "steel"),
    _t("T03", "Snag list, south bay", 25.187249, 55.263692, "light", 2, 6, "general"),
    _t("T04", "Crane-fed wall formwork", 25.187622, 55.264680, "heavy", 3, 4, "concrete"),
    _t("T05", "Fix anchor bolts", 25.187880, 55.263683, "moderate", 2, 6, "steel"),
    _t("T06", "Strip edge formwork", 25.187440, 55.264583, "moderate", 2, 6, "concrete"),
    _t("T07", "Check scaffold ties", 25.186979, 55.263795, "light", 2, 6, "general"),
    _t("T08", "Pump-place blinding slab", 25.188061, 55.263681, "moderate", 2, 6, "concrete"),
    _t("T09", "Stack deck panels", 25.187352, 55.264783, "moderate", 2, 6, "general"),
    _t("T10", "Tie starter bars", 25.188238, 55.263381, "heavy", 3, 4, "steel"),
    _t("T11", "Set out grid lines", 25.187613, 55.263985, "light", 1, 4, "general"),
    _t("T12", "Inspect rebar cover", 25.187975, 55.264079, "light", 1, 4, "steel", ["T02"]),
    _t("T13", "Lay waterproof membrane", 25.188150, 55.263581, "moderate", 2, 6, "general", ["T11"]),
    _t("T14", "Pull site cables", 25.187528, 55.264383, "moderate", 2, 6, "electrical"),
    _t("T15", "Terminate cables", 25.187436, 55.264285, "light", 1, 4, "electrical", ["T14"]),
    _t("T16", "Test lighting circuits", 25.186974, 55.263399, "light", 2, 6, "electrical"),
]

# Half the crew holds a second trade, so one trade running short does not stall the site.
_NAMES = [
    ("Rafiq", ["steel", "general"]), ("Imran", ["steel"]), ("Sajid", ["steel", "general"]),
    ("Nasir", ["steel"]), ("Bilal", ["steel", "concrete"]),
    ("Hassan", ["concrete", "general"]), ("Farhan", ["concrete"]), ("Omar", ["concrete", "general"]),
    ("Tariq", ["concrete"]),
    ("Anwar", ["general", "electrical"]), ("Zubair", ["general"]), ("Khalid", ["general", "electrical"]),
    ("Mahmoud", ["electrical"]), ("Yusuf", ["electrical", "general"]),
]
WORKERS = [dict(id=f"W{i:02d}", name=n, trades=t) for i, (n, t) in enumerate(_NAMES, 1)]


def assert_tasks_in_open_ground(buildings_geojson_path):
    """Raise if any task point is within 8 m of a building footprint."""
    to_m = Transformer.from_crs(4326, 32640, always_xy=True).transform
    feats = json.loads(Path(buildings_geojson_path).read_text())["features"]
    ground = unary_union([
        Polygon([to_m(*p) for p in f["geometry"]["coordinates"][0]]) for f in feats
    ])
    for t in TASKS:
        d = ground.distance(Point(*to_m(t["lon"], t["lat"])))
        if d < MIN_CLEARANCE_M:
            raise AssertionError(f"{t['id']} is {d:.1f} m from a building, need {MIN_CLEARANCE_M} m")


if __name__ == "__main__":
    assert_tasks_in_open_ground(Path(__file__).resolve().parents[2] / "data" / "buildings.geojson")
    print("ok, sum crew x slots =", sum(t["crew"] * t["slots"] for t in TASKS))
