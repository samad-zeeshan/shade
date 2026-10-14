"""
ACGIH heat stress screening table, turned into a per-slot load for the solver.
"""

# WBGT thresholds in degrees C for acclimatised workers, ACGIH TLV screening criteria.
# Columns are 100, 75, 50, 25 percent work per hour. None means ACGIH lists no value,
# so that work fraction is never allowed for the class.
TABLE = {
    "light": (31.0, 31.0, 32.0, 32.5),
    "moderate": (28.0, 29.0, 30.0, 31.5),
    "heavy": (None, 27.5, 29.0, 30.5),
    "very_heavy": (None, None, 28.0, 30.0),
}

# Load in twelfths of an hour per 15-minute slot. A rolling hour holds 48 units,
# so 100 percent fits 4 slots, 75 percent 3, 50 percent 2, 25 percent 1.
LOADS = (12, 16, 24, 48)
BUDGET = 48


def load(wbgt, cls):
    """Cost of one worked slot at this WBGT, or None when no work is allowed."""
    for threshold, units in zip(TABLE[cls], LOADS):
        if threshold is not None and wbgt <= threshold:
            return units
    return None
