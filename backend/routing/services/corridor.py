"""Sampling grid covering the corridor around all route options (for the weather heatmap)."""
from __future__ import annotations

import math

from .domain import LatLon, miles_to_km
from .geo import KM_PER_DEG_LAT, SpatialIndex, bounding_box, cumulative_km, sample_every

ANCHOR_STEP_KM = 5.0
MIN_SPACING_KM = 12.0
MAX_ITERATIONS = 15


def corridor_grid(routes: list[list[LatLon]], radius_miles: float, max_points: int) -> list[LatLon]:
    """Staggered grid of points within ``radius_miles`` of any route, at most ``max_points``.

    The spacing adapts to the trip: short trips get a dense grid, long trips a
    coarser one, so the heatmap request stays cheap regardless of distance.
    """
    radius_km = miles_to_km(radius_miles)
    anchors: list[LatLon] = []
    longest_km = 0.0
    for coords in routes:
        if len(coords) < 2:
            continue
        cum = cumulative_km(coords)
        longest_km = max(longest_km, cum[-1])
        anchors.extend(sample_every(coords, cum, ANCHOR_STEP_KM))
    if not anchors:
        return []

    index = SpatialIndex(anchors, cell_km=max(radius_km, 1.0))
    min_lat, min_lon, max_lat, max_lon = bounding_box(anchors)
    kx = max(math.cos(math.radians((min_lat + max_lat) / 2)), 0.1)
    pad_lat = radius_km / KM_PER_DEG_LAT
    pad_lon = pad_lat / kx

    area_km2 = max(longest_km, 1.0) * 2 * radius_km
    spacing = max(MIN_SPACING_KM, math.sqrt(area_km2 / max_points))

    points: list[LatLon] = []
    for _ in range(MAX_ITERATIONS):
        points = _grid(min_lat - pad_lat, max_lat + pad_lat, min_lon - pad_lon, max_lon + pad_lon,
                       spacing, kx, index, radius_km)
        if len(points) <= max_points:
            return points
        spacing *= 1.15
    return points[:max_points]


def _grid(lat0: float, lat1: float, lon0: float, lon1: float, spacing_km: float, kx: float,
          index: SpatialIndex, radius_km: float) -> list[LatLon]:
    dlat = spacing_km / KM_PER_DEG_LAT
    dlon = dlat / kx
    out: list[LatLon] = []
    row = 0
    lat = lat0
    while lat <= lat1:
        lon = lon0 + (dlon / 2 if row % 2 else 0.0)  # staggered rows cover the corridor evenly
        while lon <= lon1:
            if index.has_within((lat, lon), radius_km):
                out.append((round(lat, 4), round(lon, 4)))
            lon += dlon
        lat += dlat
        row += 1
    return out
