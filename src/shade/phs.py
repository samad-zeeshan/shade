"""
How long one run of work may last before core temperature reaches 38 C, from the PHS model.

PHS is Malchaire et al. (2001), standardised as ISO 7933, as implemented in pythermalcomfort.
"""
import numpy as np
from pythermalcomfort.models import phs

from shade.limits import M

CAP_MIN = 240  # minutes; a run this long has no practical limit within a shift
# pythermalcomfort's default body, 75 kg and 1.8 m. PHS takes metabolic rate per square metre of skin.
A_DUBOIS = 0.202 * 75 ** 0.425 * 1.8 ** 0.725
MET_W_M2 = 58.15


def _p_a(tdb, rh):
    # Vapour pressure in kPa, same formula pythermalcomfort uses for the 2023 model.
    return 0.6105 * np.exp(17.27 * tdb / (tdb + 237.3)) * rh / 100


def run_minutes(cls, weather, tr):
    """Minutes until rectal temperature reaches 38 C, per slot, and the number of clipped cells.

    Inputs outside the ISO 7933 range make the model return NaN, so they are clipped into range.
    """
    ta = np.array([w["ta"] for w in weather], dtype=float)
    rh = np.array([w["rh"] for w in weather], dtype=float)
    v = np.array([w["wind"] for w in weather], dtype=float)
    tr = np.asarray(tr, dtype=float)
    met_w = M[cls] / A_DUBOIS
    tdb_c = np.clip(ta, 15, 50)
    tr_c = np.clip(tr, 0, 60)
    v_c = np.clip(v, 0, 3)
    pa = _p_a(tdb_c, rh)
    rh_c = np.where(pa > 4.5, rh * 4.5 / pa, np.where(pa < 0.5, rh * 0.5 / pa, rh))
    met_c = np.clip(met_w, 100, 450)
    clipped = (tdb_c != ta) | (tr_c != tr) | (v_c != v) | (rh_c != rh) | (met_c != met_w)
    r = phs(tdb=tdb_c, tr=tr_c, v=v_c, rh=rh_c, met=met_c / MET_W_M2, clo=0.5, posture="standing",
            duration=CAP_MIN, acclimatized=100, round_output=False)
    d = np.nan_to_num(np.asarray(r.d_lim_t_re, dtype=float), nan=0.0)
    return [int(min(CAP_MIN, np.floor(x))) for x in d], int(clipped.sum())


def run_table(tasks, weather, tr):
    """run_min[t][s] in whole minutes, run cap in slots, and total clipped cells."""
    run_min, n_clipped = [], 0
    for t, task in enumerate(tasks):
        mins, c = run_minutes(task["cls"], weather, tr[t])
        run_min.append(mins)
        n_clipped += c
    caps = [[m // 15 for m in row] for row in run_min]
    return run_min, caps, n_clipped
