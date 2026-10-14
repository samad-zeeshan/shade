"""End-to-end build on the committed data, checked against the data.json schema."""
import json
import tempfile
from pathlib import Path

from shade.build import build

TOP = {"meta", "weather", "sun", "buildings", "shadows", "tasks", "workers", "scenarios"}
METRICS = {"overtime_hours", "unscheduled_hours", "violation_hours", "tasks_done_by_17",
           "peak_wbgt_worked", "mean_shade_worked"}


def test_build():
    out = Path(tempfile.mkdtemp()) / "data.json"
    build(out=out, time_limit=5)
    assert out.stat().st_size < 6e6
    d = json.loads(out.read_text(encoding="utf-8"))
    assert set(d) == TOP
    assert d["meta"]["n_slots"] == 60 and d["meta"]["ban_slots"] == [30, 39]
    for key in ("weather", "sun", "shadows"):
        assert len(d[key]) == 60
    assert d["buildings"]["type"] == "FeatureCollection"
    for t in d["tasks"]:
        assert len(t["shade"]) == len(t["wbgt"]) == len(t["load"]) == 60
    assert set(d["scenarios"]) == {"ban_only", "sun_blind", "shade_aware"}
    for sc in d["scenarios"].values():
        assert set(sc) == {"label", "metrics", "assign"} and set(sc["metrics"]) == METRICS
        assert len(sc["assign"]) == len(d["workers"]) and all(len(r) == 60 for r in sc["assign"])
        assert all(r[s] is None for r in sc["assign"] for s in range(30, 40))
    tasks = {t["id"]: t for t in d["tasks"]}
    for row in d["scenarios"]["shade_aware"]["assign"]:
        for s, tid in enumerate(row):
            if tid is not None:
                assert tasks[tid]["load"][s] is not None
