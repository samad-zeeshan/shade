"""
Assign workers to tasks per 15-minute slot with CP-SAT, then score any assignment.

The same metrics function scores all three scenarios against the true per-spot heat.
"""
import time

from ortools.sat.python import cp_model

from shade.limits import BUDGET

WINDOW = 4  # slots in a rolling hour


def solve(tasks, workers, loads, ban, n_slots=60, shift_end=48, time_limit=60.0):
    """loads[t][s] is the heat load or None (forbidden). loads=None turns the heat rule off."""
    m = cp_model.CpModel()
    T, W, S = range(len(tasks)), range(len(workers)), range(n_slots)
    ok = lambda t, s: s not in ban and (loads is None or loads[t][s] is not None)

    # Only create x where the trade matches and the slot is open, which keeps the model small.
    x = {(w, t, s): m.new_bool_var(f"x{w}_{t}_{s}")
         for w in W for t in T if tasks[t]["trade"] in workers[w]["trades"]
         for s in S if ok(t, s)}
    a = {(t, s): m.new_bool_var(f"a{t}_{s}") for t in T for s in S if ok(t, s)}
    u = [m.new_int_var(0, tasks[t]["slots"] * tasks[t]["crew"], f"u{t}") for t in T]
    last = [m.new_int_var(0, n_slots, f"last{t}") for t in T]
    start = [m.new_int_var(0, n_slots, f"start{t}") for t in T]

    for w in W:
        for s in S:
            m.add_at_most_one(x[w, t, s] for t in T if (w, t, s) in x)
    for (t, s), at in a.items():
        crew = tasks[t]["crew"]
        m.add(sum(x[w, t, s] for w in W if (w, t, s) in x) == crew * at)
        m.add(last[t] >= s * at)
        m.add(start[t] <= s + n_slots * (1 - at))
    for t in T:
        crew = tasks[t]["crew"]
        m.add(crew * sum(a[t, s] for s in S if (t, s) in a) + u[t] == tasks[t]["slots"] * crew)

    # Precedence: B may start only after A has run its last slot and A has no unscheduled slack.
    index = {task["id"]: t for t, task in enumerate(tasks)}
    for b in T:
        for aid in tasks[b]["after"]:
            p = index[aid]
            done = m.new_bool_var(f"done{p}_{b}")
            m.add(u[p] == 0).only_enforce_if(done)
            for s in S:
                if (b, s) in a:
                    m.add_implication(a[b, s], done)
            m.add(last[p] + 1 <= start[b])

    # Heat: in every rolling hour each worker's summed load stays within 48 twelfths.
    if loads is not None:
        for w in W:
            for k in range(n_slots - WINDOW + 1):
                terms = [loads[t][s] * x[w, t, s] for t in T for s in range(k, k + WINDOW) if (w, t, s) in x]
                if terms:
                    m.add(sum(terms) <= BUDGET)

    overtime = sum(v for (w, t, s), v in x.items() if s >= shift_end)
    # Weights rank goals: finish all work first, then avoid overtime, then finish early.
    m.minimize(1000 * sum(u) + 10 * overtime + sum(last))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    t0 = time.perf_counter()
    status = solver.solve(m)
    wall = time.perf_counter() - t0
    name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": name, "objective": None, "wall_s": wall, "assign": None}
    assign = [[None] * n_slots for _ in W]
    for (w, t, s), v in x.items():
        if solver.value(v):
            assign[w][s] = tasks[t]["id"]
    return {"status": name, "objective": solver.objective_value, "wall_s": wall,
            "bound": solver.best_objective_bound, "n_x": len(x), "assign": assign}


def metrics(assign, tasks, loads, wbgt, shade, shift_end=48):
    """Score an assignment with the true heat. loads/wbgt/shade are indexed [task][slot]."""
    index = {task["id"]: t for t, task in enumerate(tasks)}
    n_slots = len(assign[0])
    done = [0] * len(tasks)
    late = [False] * len(tasks)
    overtime = violation = 0
    worked = []
    for row in assign:
        bad = set()
        cost = []
        for s, tid in enumerate(row):
            if tid is None:
                cost.append(0)
                continue
            t = index[tid]
            done[t] += 1
            late[t] |= s >= shift_end
            overtime += s >= shift_end
            worked.append((t, s))
            # A slot with no allowed work counts as more than a full hour of budget.
            cost.append(loads[t][s] if loads[t][s] is not None else BUDGET + 1)
        for k in range(n_slots - WINDOW + 1):
            if sum(cost[k:k + WINDOW]) > BUDGET:
                bad.update(s for s in range(k, k + WINDOW) if row[s] is not None)
        violation += len(bad)
    unscheduled = sum(task["slots"] * task["crew"] - done[t] for t, task in enumerate(tasks))
    finished = sum(1 for t, task in enumerate(tasks)
                   if done[t] == task["slots"] * task["crew"] and not late[t])
    return {
        "overtime_hours": overtime / 4,
        "unscheduled_hours": unscheduled / 4,
        "violation_hours": violation / 4,
        "tasks_done_by_17": finished,
        "peak_wbgt_worked": max((wbgt[t][s] for t, s in worked), default=None),
        "mean_shade_worked": round(sum(shade[t][s] for t, s in worked) / len(worked), 2) if worked else None,
    }
