"""Geodesy helpers: distances, interpolation along polylines, simplification, spatial hashing."""
from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from typing import Iterable, Sequence

from .domain import LatLon

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = 111.195


def haversine_km(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def fast_distance_km(a: LatLon, b: LatLon) -> float:
    """Equirectangular approximation; accurate to <0.5% for distances under ~200 km."""
    kx = math.cos(math.radians((a[0] + b[0]) / 2))
    dx = (b[1] - a[1]) * kx * KM_PER_DEG_LAT
    dy = (b[0] - a[0]) * KM_PER_DEG_LAT
    return math.hypot(dx, dy)


def initial_bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(start: LatLon, bearing_deg: float, distance_km: float) -> LatLon:
    """Point reached travelling ``distance_km`` from ``start`` along ``bearing_deg``."""
    lat1, lon1 = math.radians(start[0]), math.radians(start[1])
    brng = math.radians(bearing_deg)
    d = distance_km / EARTH_RADIUS_KM
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brng))
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    lon2 = (lon2 + 3 * math.pi) % (2 * math.pi) - math.pi
    return (math.degrees(lat2), math.degrees(lon2))


def cumulative_km(coords: Sequence[LatLon]) -> list[float]:
    out = [0.0]
    for i in range(1, len(coords)):
        out.append(out[-1] + haversine_km(coords[i - 1], coords[i]))
    return out


def locate_along(coords: Sequence[LatLon], cum: Sequence[float], target: float) -> tuple[LatLon, int, float]:
    """Position at cumulative value ``target`` (same unit as ``cum``).

    Returns ``(point, segment_index, fraction)``: the point lies on the segment
    ``coords[i] -> coords[i + 1]`` at ``fraction`` of its length.
    """
    n = len(coords)
    if n == 0:
        raise ValueError("empty polyline")
    if n == 1 or target <= 0:
        return coords[0], 0, 0.0
    if target >= cum[-1]:
        return coords[-1], n - 2, 1.0
    i = bisect_right(cum, target) - 1
    i = max(0, min(i, n - 2))
    seg = cum[i + 1] - cum[i]
    frac = 0.0 if seg <= 0 else (target - cum[i]) / seg
    a, b = coords[i], coords[i + 1]
    return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac), i, frac


def interpolate(values: Sequence[float], index: int, frac: float) -> float:
    if index >= len(values) - 1:
        return values[-1]
    return values[index] + (values[index + 1] - values[index]) * frac


def sample_every(coords: Sequence[LatLon], cum: Sequence[float], step_km: float) -> list[LatLon]:
    """Points at regular intervals along a polyline, always including both ends."""
    if not coords:
        return []
    total = cum[-1]
    out: list[LatLon] = []
    d = 0.0
    while d < total:
        out.append(locate_along(coords, cum, d)[0])
        d += step_km
    out.append(coords[-1])
    return out


def simplify(coords: Sequence[LatLon], tolerance_deg: float) -> list[LatLon]:
    """Iterative Douglas-Peucker in a locally isotropic degree space."""
    n = len(coords)
    if n <= 2 or tolerance_deg <= 0:
        return list(coords)
    mean_lat = sum(c[0] for c in coords) / n
    kx = max(math.cos(math.radians(mean_lat)), 0.05)
    pts = [(c[0], c[1] * kx) for c in coords]
    keep = [False] * n
    keep[0] = keep[-1] = True
    tol2 = tolerance_deg * tolerance_deg
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e <= s + 1:
            continue
        ax, ay = pts[s]
        bx, by = pts[e]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best = -1.0
        best_i = -1
        for i in range(s + 1, e):
            px, py = pts[i]
            if seg2 == 0.0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / seg2
                t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
                qx, qy = ax + t * dx, ay + t * dy
                d2 = (px - qx) ** 2 + (py - qy) ** 2
            if d2 > best:
                best, best_i = d2, i
        if best > tol2:
            keep[best_i] = True
            stack.append((s, best_i))
            stack.append((best_i, e))
    return [c for c, k in zip(coords, keep) if k]


def bounding_box(coords: Iterable[LatLon]) -> tuple[float, float, float, float]:
    lats: list[float] = []
    lons: list[float] = []
    for lat, lon in coords:
        lats.append(lat)
        lons.append(lon)
    return min(lats), min(lons), max(lats), max(lons)


class SpatialIndex:
    """Uniform grid hash answering "is there a point within r km?" quickly."""

    def __init__(self, points: Iterable[LatLon], cell_km: float) -> None:
        pts = list(points)
        self.cell_km = cell_km
        self.cell_lat = cell_km / KM_PER_DEG_LAT
        mean_lat = sum(p[0] for p in pts) / len(pts) if pts else 0.0
        self.cell_lon = self.cell_lat / max(math.cos(math.radians(mean_lat)), 0.1)
        self.cells: dict[tuple[int, int], list[LatLon]] = defaultdict(list)
        for p in pts:
            self.cells[self._key(p)].append(p)

    def _key(self, p: LatLon) -> tuple[int, int]:
        return (math.floor(p[0] / self.cell_lat), math.floor(p[1] / self.cell_lon))

    def min_distance_km(self, p: LatLon, max_km: float) -> float | None:
        """Distance to the nearest indexed point if it is within ``max_km``, else ``None``."""
        rings = math.ceil(max_km / self.cell_km)
        ki, kj = self._key(p)
        best: float | None = None
        for di in range(-rings, rings + 1):
            for dj in range(-rings, rings + 1):
                for q in self.cells.get((ki + di, kj + dj), ()):
                    d = fast_distance_km(p, q)
                    if d <= max_km and (best is None or d < best):
                        best = d
        return best

    def has_within(self, p: LatLon, max_km: float) -> bool:
        return self.min_distance_km(p, max_km) is not None
