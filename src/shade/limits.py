"""
NIOSH heat limit as a 1-hour average, turned into a per-slot load for the solver.
"""
import math

# Metabolic rate in watts per class, and the rate while resting.
M = {"light": 180, "moderate": 300, "heavy": 415, "very_heavy": 520}
M_REST = 115

# Load in twelfths of an hour per 15-minute slot. A rolling hour holds 48 units,
# so 100 percent fits 4 slots, 75 percent 3, 50 percent 2, 25 percent 1.
FRACTIONS = (1.0, 0.75, 0.5, 0.25)
LOADS = (12, 16, 24, 48)
BUDGET = 48
WORK_MIN = {12: 60, 16: 45, 24: 30, 48: 15, None: 0}


def rel(m):
    # NIOSH (2016) Publication 2016-106, chapter 8, page 125. REL [C WBGT] = 56.7 - 11.5 log10 M, M in watts.
    return 56.7 - 11.5 * math.log10(m)


def load(wbgt_work, wbgt_rest, cls):
    """Cost of one worked slot, or None when no work fraction keeps the hour under the REL.

    Both WBGT and metabolic rate are averaged over the hour, with rest taken in shade.
    """
    for p, units in zip(FRACTIONS, LOADS):
        wbgt_twa = p * wbgt_work + (1 - p) * wbgt_rest
        m_twa = p * M[cls] + (1 - p) * M_REST
        if wbgt_twa <= rel(m_twa):
            return units
    return None
