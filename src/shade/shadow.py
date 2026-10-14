"""
Building shadow polygons for a sun position, and shade fraction around a point.
"""
import math

import shapely
from shapely.geometry import Point, Polygon
from shapely.affinity import translate

MIN_ELEVATION = 1.0
MAX_LENGTH = 600.0


def shadow_offset(h, az, el):
    """Ground offset (dx east, dy north) of the roof outline, in metres."""
    length = min(h / math.tan(math.radians(el)), MAX_LENGTH)
    # Sun at azimuth az throws the shadow toward az + 180, so both components flip sign.
    return -length * math.sin(math.radians(az)), -length * math.cos(math.radians(az))


def building_shadow(poly, h, az, el):
    dx, dy = shadow_offset(h, az, el)
    pts = list(poly.exterior.coords)
    # Sweep every edge instead of a convex hull, so L-shaped and concave towers stay right.
    quads = [Polygon([p, q, (q[0] + dx, q[1] + dy), (p[0] + dx, p[1] + dy)]) for p, q in zip(pts, pts[1:])]
    parts = [poly, translate(poly, dx, dy)] + [g for g in quads if g.area > 0]
    return shapely.union_all(parts)


def slot_shadow(buildings, az, el):
    """Return (union geometry or None, night flag). Night means the whole site is in shade."""
    if el <= MIN_ELEVATION:
        return None, True
    union = shapely.union_all([building_shadow(p, h, az, el) for p, h in buildings])
    return union.simplify(0.5), False


def shade_fraction(point_m, shadow_union, radius=6.0, night=False):
    if night:
        return 1.0
    if shadow_union is None or shadow_union.is_empty:
        return 0.0
    disc = Point(point_m).buffer(radius, quad_segs=16)
    return round(min(1.0, disc.intersection(shadow_union).area / disc.area), 3)
