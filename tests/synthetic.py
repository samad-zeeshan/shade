"""Six synthetic towers, 40 to 120 m tall, for running the shadow code without OSM data."""
from shapely.geometry import box

from shade.build import TO_M
from shade.sun import LAT, LON


def towers():
    cx, cy = TO_M(LON, LAT)
    spots = [(-120, 0, 120), (120, 0, 100), (0, 140, 80), (0, -140, 60), (-90, 110, 40), (100, -100, 70)]
    return [(box(cx + dx - 15, cy + dy - 15, cx + dx + 15, cy + dy + 15), h) for dx, dy, h in spots]
