"""Shadow direction, length and shade fraction on a single box tower."""
from shapely.geometry import box

from shade.shadow import shade_fraction, slot_shadow

BOX = [(box(0, 0, 10, 10), 30.0)]


def test_sun_south_shadow_goes_north():
    union, night = slot_shadow(BOX, 180, 45)
    assert not night
    minx, miny, maxx, maxy = union.bounds
    assert abs(maxy - 40) < 0.6 and abs(miny) < 0.6
    # The default 6 m disc is wider than the 10 m shadow strip, so use 4 m here.
    assert shade_fraction((5, 25), union, radius=4) == 1.0
    assert shade_fraction((5, 60), union) == 0.0


def test_sun_east_shadow_goes_west():
    union, _ = slot_shadow(BOX, 90, 45)
    minx, _, maxx, _ = union.bounds
    assert abs(minx + 30) < 0.6 and abs(maxx - 10) < 0.6


def test_partial_and_edge():
    union, _ = slot_shadow(BOX, 180, 45)
    # Disc centred on the shadow's east edge is half covered.
    assert abs(shade_fraction((10, 25), union) - 0.5) < 0.02
    assert shade_fraction((5, 25), None) == 0.0


def test_night_and_length_cap():
    union, night = slot_shadow(BOX, 180, 0.5)
    assert night and union is None
    assert shade_fraction((999, 999), None, night=True) == 1.0
    union, _ = slot_shadow(BOX, 180, 1.5)
    assert union.bounds[3] <= 10 + 600 + 0.6


def test_l_shape_not_hull():
    from shapely.geometry import Polygon
    ell = Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)])
    union, _ = slot_shadow([(ell, 1.0)], 180, 45)
    # Inside the notch of the L, beyond the 1 m shadow reach, must stay sunlit.
    assert shade_fraction((22, 22), union, radius=2) == 0.0


def test_synthetic_towers_morning_shadow_falls_west():
    from synthetic import towers
    from shade.sun import sun_table

    sun = sun_table()[8]  # 07:00, sun in the east
    union, night = slot_shadow(towers(), sun["azimuth"], sun["elevation"])
    tall, h = towers()[1]  # 100 m tower east of centre
    c = tall.centroid
    assert not night
    import math
    ex, ny = math.sin(math.radians(sun["azimuth"])), math.cos(math.radians(sun["azimuth"]))
    assert shade_fraction((c.x - 60 * ex, c.y - 60 * ny), union, radius=3) == 1.0
    assert shade_fraction((c.x + 60 * ex, c.y + 60 * ny), union, radius=3) == 0.0
