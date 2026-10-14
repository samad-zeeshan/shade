"""Tiny CP-SAT instance: crew, ban, rolling budget and precedence."""
import time

from shade.limits import BUDGET
from shade.solve import metrics, solve

TASKS = [
    {"id": "A", "crew": 2, "slots": 2, "trade": "steel", "after": []},
    {"id": "B", "crew": 1, "slots": 2, "trade": "steel", "after": ["A"]},
]
WORKERS = [{"id": "W1", "trades": ["steel"]}, {"id": "W2", "trades": ["steel"]}]
BAN = {2}
# Task A is heavy enough that only 2 of 4 slots fit in an hour.
LOADS = [[24] * 8, [12] * 8]


def test_tiny():
    t0 = time.perf_counter()
    r = solve(TASKS, WORKERS, LOADS, BAN, n_slots=8, shift_end=6, time_limit=5)
    assert time.perf_counter() - t0 < 5
    assert r["status"] == "OPTIMAL"
    assign = r["assign"]
    for s in range(8):
        col = [row[s] for row in assign]
        assert col.count("A") in (0, 2)  # full crew or nothing
    assert all(row[2] is None for row in assign)  # ban slot empty
    a_slots = [s for s in range(8) if assign[0][s] == "A"]
    b_slots = [s for s in range(8) for row in assign if row[s] == "B"]
    assert len(a_slots) == 2 and len(b_slots) == 2
    assert max(a_slots) < min(b_slots)  # precedence
    for row in assign:
        cost = [LOADS[0 if v == "A" else 1][s] if v else 0 for s, v in enumerate(row)]
        assert all(sum(cost[k:k + 4]) <= BUDGET for k in range(5))
    m = metrics(assign, TASKS, LOADS, [[30.0] * 8] * 2, [[0.5] * 8] * 2, shift_end=6)
    assert m["violation_hours"] == 0 and m["unscheduled_hours"] == 0 and m["tasks_done_by_17"] == 2


def test_metrics_counts_violation_and_overtime():
    tasks = [{"id": "A", "crew": 1, "slots": 4, "trade": "steel", "after": []}]
    assign = [["A", "A", "A", "A", None, None, None, None]]
    m = metrics(assign, tasks, [[24] * 8], [[31.0] * 8], [[0.0] * 8], shift_end=3)
    assert m["violation_hours"] == 1.0  # 4 slots at 24 each = 96 > 48
    assert m["overtime_hours"] == 0.25
    assert m["tasks_done_by_17"] == 0
    assert m["peak_wbgt_worked"] == 31.0


def test_run_cap_one_slot():
    # One worker, one task of 3 slots, cap 1: the worker may never do two slots in a row on it.
    tasks = [{"id": "A", "crew": 1, "slots": 3, "trade": "steel", "after": []}]
    workers = [{"id": "W1", "trades": ["steel"]}]
    caps = [[1] * 8]
    r = solve(tasks, workers, [[12] * 8], set(), n_slots=8, shift_end=8, time_limit=5, caps=caps)
    row = r["assign"][0]
    assert row.count("A") == 3
    assert all(not (row[s] and row[s + 1]) for s in range(7))
    m = metrics(r["assign"], tasks, [[12] * 8], [[30.0] * 8], [[0.0] * 8], shift_end=8, caps=caps)
    assert m["runs_over_phs"] == 0 and m["longest_run_min"] == 15


def test_metrics_flag_long_runs():
    tasks = [{"id": "A", "crew": 1, "slots": 3, "trade": "steel", "after": []}]
    assign = [["A", "A", "A", None]]
    m = metrics(assign, tasks, [[12] * 4], [[30.0] * 4], [[0.0] * 4], shift_end=4, caps=[[1] * 4])
    assert m["longest_run_min"] == 45 and m["runs_over_phs"] == 3
