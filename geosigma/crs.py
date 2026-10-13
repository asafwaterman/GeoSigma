"""Coordinate handling for Israeli grids.

EPSG:2039  Israeli Transverse Mercator (ITM, "New Israel Grid"), used by recent surveys.
EPSG:28193 Palestine 1923 / Israeli CS Grid ("Old Israel Grid"), used by older reports.
Old reports often print the Old Israel Grid without the false northing offset of
1,000,000 m or as kilometres; ``normalise_old_grid`` handles both.
"""
from __future__ import annotations

from functools import lru_cache

from pyproj import Transformer

ITM = "EPSG:2039"
OLD_GRID = "EPSG:28193"
WGS84 = "EPSG:4326"

# Rough bounding box of Israel and the Golan, in WGS84 lon/lat.
ISRAEL_BBOX = (34.2, 29.4, 35.95, 33.45)


@lru_cache(maxsize=None)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def normalise_old_grid(x: float, y: float) -> tuple[float, float]:
    """Return Old Israel Grid metres with the 1,000,000 m false northing applied."""
    if x < 1000 and y < 1500:  # printed in kilometres
        x, y = x * 1000, y * 1000
    if y < 500_000:  # printed without the false northing
        y += 1_000_000
    return x, y


def to_wgs84(x: float, y: float, crs: str) -> tuple[float, float]:
    """Return (lon, lat)."""
    if crs == WGS84:
        return x, y
    if crs == OLD_GRID:
        x, y = normalise_old_grid(x, y)
    return _transformer(crs, WGS84).transform(x, y)


def to_itm(x: float, y: float, crs: str) -> tuple[float, float]:
    if crs == ITM:
        return x, y
    if crs == OLD_GRID:
        x, y = normalise_old_grid(x, y)
    return _transformer(crs, ITM).transform(x, y)


def inside_israel(lon: float, lat: float) -> bool:
    w, s, e, n = ISRAEL_BBOX
    return w <= lon <= e and s <= lat <= n
