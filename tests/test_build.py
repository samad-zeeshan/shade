"""End-to-end build of one plot7 run on the committed data, checked against the run file schema."""
import json
import tempfile
from pathlib import Path

from shapely.geometry import box

from shade.build import build, grid_points, manifest, solver_info, summary
from shade.scenario import load_site

WEATHER = Path(__file__).parent / "fixtures" / "weather_2026-07-15.json"
TOP = {"meta", "weather", "sun", "buildings", "shadows", "tasks", "workers", "scenarios", "grid"}
METRICS = {"overtime_hours", "unscheduled_hours", "violation_hours", "tasks_done_by_17",
           "peak_wbgt_worked", "mean_shade_worked", "longest_run_min", "runs_over_phs"}
SOURCE_KEYS = ["liljegren2008", "brimicombe2022", "niosh2016", "garzon2017", "malchaire2001"]


def test_build():
    out = Path(tempfile.mkdtemp()) / "run.json"
    build(load_site("plot7"), WEATHER, out=out, time_limit=5)
    assert out.stat().st_size < 6e6
    d = json.loads(out.read_text(encoding="utf-8"))
    assert set(d) == TOP
    assert d["meta"]["n_slots"] == 60 and d["meta"]["ban_slots"] == [30, 39]
    assert d["meta"]["site_id"] == "plot7" and d["meta"]["run_id"] == "plot7-2026-07-15"
    assert [x["key"] for x in d["meta"]["sources"]] == SOURCE_KEYS
    assert d["meta"]["weather_source"] and "limits_source" not in d["meta"] and "wbgt_source" not in d["meta"]
    for key in ("weather", "sun", "shadows"):
        assert len(d[key]) == 60
    assert all("wbgt_rest" in w for w in d["weather"])
    assert d["buildings"]["type"] == "FeatureCollection"
    for t in d["tasks"]:
        assert len(t["shade"]) == len(t["wbgt"]) == len(t["load"]) == len(t["work_min"]) == len(t["run_min"]) == 60
        assert set(t["work_min"]) <= {0, 15, 30, 45, 60} and all(0 <= m <= 240 for m in t["run_min"])
    assert set(d["scenarios"]) == {"ban_only", "sun_blind", "shade_aware"}
    for sc in d["scenarios"].values():
        assert set(sc) == {"label", "metrics", "assign", "solver"} and set(sc["metrics"]) == METRICS
        assert set(sc["solver"]) == {"status", "objective", "bound", "gap_pct"}
        assert len(sc["assign"]) == len(d["workers"]) and all(len(r) == 60 for r in sc["assign"])
        assert all(r[s] is None for r in sc["assign"] for s in range(30, 40))
    tasks = {t["id"]: t for t in d["tasks"]}
    for row in d["scenarios"]["shade_aware"]["assign"]:
        for s, tid in enumerate(row):
            if tid is not None:
                assert tasks[tid]["load"][s] is not None
    g = d["grid"]
    assert 0 < len(g["points"]) <= 500 and g["classes"] == ["light", "moderate", "heavy", "very_heavy"]
    assert len(json.dumps(g, separators=(",", ":"))) < 200_000
    for c in g["classes"]:
        assert len(g["work"][c]) == len(g["points"])
        assert all(len(r) == 60 and set(r) <= set("01234") for r in g["work"][c])
    # Lighter work is never allowed fewer minutes than heavier work at the same spot and slot.
    for a, b in zip(g["work"]["light"], g["work"]["very_heavy"]):
        assert all(x >= y for x, y in zip(a, b))
    entry = summary(d)
    assert entry["file"] == "runs/plot7-2026-07-15.json" and isinstance(entry["morning_rh"], int)


def test_grid_step_grows_to_cap():
    step, xs, ys = grid_points(box(0, 0, 300, 300), step=6, cap=500)
    assert len(xs) <= 500 and step > 6
    step, xs, _ = grid_points(box(0, 0, 60, 60), step=6, cap=500)
    assert step == 6 and len(xs) == 100


def test_solver_gap():
    assert solver_info({"status": "OPTIMAL", "objective": 10.0, "bound": 10.0})["gap_pct"] == 0.0
    assert solver_info({"status": "FEASIBLE", "objective": 200.0, "bound": 150.0})["gap_pct"] == 25.0


def test_manifest_order_and_default():
    def e(id, city, date, blind, shade):
        return {"id": id, "city": city, "date": date, "blind_extra_h": blind, "shade_extra_h": shade}
    m = manifest([e("b", "Dubai", "2025-07-02", 5, 1), e("a", "Abu Dhabi", "2025-07-01", 3, 3),
                  e("c", "Dubai", "2025-07-01", 9, 5)])
    assert [r["id"] for r in m["runs"]] == ["a", "c", "b"]
    assert m["default"] == "c"  # tie at 4 hours saved goes to the first run in order
