"""Route options from an OSRM-compatible API, topped up with synthesized detours.

OSRM's ``alternatives`` parameter usually yields only one or two alternatives
for long trips. When fewer than the requested number of distinct routes come
back, we route through via-points offset perpendicular to the fastest route
and keep the candidates that are genuinely different (see ``route_similarity``).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence

import requests
from django.conf import settings
from django.core.cache import cache

from ..exceptions import RoutingError
from .domain import LatLon, RouteOption
from .geo import (
    SpatialIndex,
    cumulative_km,
    destination_point,
    initial_bearing_deg,
    locate_along,
    sample_every,
)
from .http import get_session, timeout

log = logging.getLogger(__name__)

SIMILARITY_SAMPLE_KM = 3.0
SIMILARITY_MATCH_KM = 2.5
MAX_SIMILARITY_PROVIDER = 0.9  # alternatives returned by the routing API
MAX_SIMILARITY_DETOUR = 0.7  # synthesized detours must differ more
MAX_DETOUR_DURATION_FACTOR = 1.5  # never propose detours >50% slower than the fastest route
DETOUR_OFFSET_FRACTION = 0.12  # via-point offset as a fraction of the trip length ...
DETOUR_OFFSET_MIN_KM = 12.0  # ... clamped so short trips still get a real detour
DETOUR_OFFSET_MAX_KM = 160.0  # ... and long trips diverge enough to pass the similarity test in one round

_ROAD_REF_RE = re.compile(r"^(I|US|SR|CR|[A-Z]{2})[ -](\d+[A-Z]?)$")


def _normalize_ref(ref: str) -> str:
    first = ref.split(";")[0].strip()
    match = _ROAD_REF_RE.match(first)
    return f"{match.group(1)}-{match.group(2)}" if match else first


def major_roads(route_json: dict, limit: int = 2) -> list[str]:
    """The roads carrying most of the route's distance, e.g. ``["I-80", "I-15"]``."""
    total_m = float(route_json.get("distance") or 0.0)
    by_road: dict[str, float] = {}
    for leg in route_json.get("legs", []):
        for step in leg.get("steps", []):
            label = step.get("ref") or step.get("name")
            if not label:
                continue
            label = _normalize_ref(label)
            by_road[label] = by_road.get(label, 0.0) + float(step.get("distance", 0.0))
    ranked = sorted(by_road.items(), key=lambda kv: -kv[1])
    threshold = max(0.08 * total_m, 15_000.0)
    return [name for name, dist in ranked[:limit] if dist >= threshold]


def parse_osrm_route(route_json: dict, duration_factor: float = 1.0, source: str = "osrm") -> RouteOption:
    coords = [(float(lat), float(lon)) for lon, lat in route_json["geometry"]["coordinates"]]
    if len(coords) < 2:
        raise RoutingError("Routing service returned an empty geometry.")

    total_km = float(route_json["distance"]) / 1000.0
    total_s = float(route_json["duration"]) * duration_factor

    dists: list[float] = []
    durs: list[float] = []
    for leg in route_json.get("legs", []):
        annotation = leg.get("annotation") or {}
        dists.extend(annotation.get("distance") or [])
        durs.extend(annotation.get("duration") or [])

    if len(dists) == len(coords) - 1 and len(durs) == len(coords) - 1:
        # Per-edge annotations give the true time profile along the geometry.
        cum_km = [0.0]
        cum_s = [0.0]
        for d, t in zip(dists, durs):
            cum_km.append(cum_km[-1] + d / 1000.0)
            cum_s.append(cum_s[-1] + t)
        if cum_km[-1] > 0:
            cum_km = [v * total_km / cum_km[-1] for v in cum_km]
        if cum_s[-1] > 0:
            cum_s = [v * total_s / cum_s[-1] for v in cum_s]
    else:
        # Fallback: assume time accrues proportionally to distance.
        cum_km = cumulative_km(coords)
        scale = total_km / cum_km[-1] if cum_km[-1] > 0 else 1.0
        cum_km = [v * scale for v in cum_km]
        cum_s = [v / total_km * total_s if total_km > 0 else 0.0 for v in cum_km]

    return RouteOption(
        coords=coords, cum_km=cum_km, cum_s=cum_s, source=source, major_roads=major_roads(route_json)
    )


class OSRMRouter:
    def __init__(
        self,
        base_url: str | None = None,
        profile: str | None = None,
        duration_factor: float | None = None,
    ) -> None:
        cfg = settings.TRUCK_ROUTING
        self.base_url = (base_url or cfg["OSRM_BASE_URL"]).rstrip("/")
        self.profile = profile or cfg["OSRM_PROFILE"]
        self.duration_factor = cfg["TRUCK_DURATION_FACTOR"] if duration_factor is None else duration_factor
        self.cache_seconds = cfg["ROUTE_CACHE_SECONDS"]

    def route(self, waypoints: Sequence[LatLon], alternatives: int = 1, source: str = "osrm") -> list[RouteOption]:
        if len(waypoints) < 2:
            raise ValueError("at least two waypoints are required")
        coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
        url = f"{self.base_url}/route/v1/{self.profile}/{coord_str}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration,distance",
            "steps": "true",
            # OSRM only computes alternatives for two-waypoint requests.
            "alternatives": str(alternatives) if alternatives > 1 and len(waypoints) == 2 else "false",
        }
        key = "osrm:" + hashlib.sha1(json.dumps([url, params, self.duration_factor, source]).encode()).hexdigest()
        cached = cache.get(key)
        if cached is not None:
            return cached

        try:
            resp = get_session().get(url, params=params, timeout=timeout())
        except requests.RequestException as exc:
            raise RoutingError(f"Routing service unreachable: {exc}") from exc
        try:
            payload = resp.json()
        except ValueError as exc:
            raise RoutingError(
                f"Routing service returned an invalid response (HTTP {resp.status_code})."
            ) from exc

        code = payload.get("code")
        if code != "Ok":
            if code in {"NoRoute", "NoSegment"}:
                raise RoutingError(
                    "No drivable route was found between these locations.",
                    status_code=400,
                    code="no_route",
                )
            raise RoutingError(f"Routing service error: {payload.get('message') or code or resp.status_code}")

        routes = [parse_osrm_route(r, self.duration_factor, source) for r in payload.get("routes", [])]
        cache.set(key, routes, self.cache_seconds)
        return routes


def _coverage(points: list[LatLon], reference: list[LatLon]) -> float:
    if not points or not reference:
        return 0.0
    index = SpatialIndex(reference, cell_km=SIMILARITY_MATCH_KM)
    hits = sum(1 for p in points if index.has_within(p, SIMILARITY_MATCH_KM))
    return hits / len(points)


def route_similarity(a: RouteOption, b: RouteOption) -> float:
    """Fraction of one route lying within ~2.5 km of the other (the larger of both directions).

    Taking the maximum means a route that merely adds a spur to another one is
    still considered a duplicate (the shorter route is fully contained).
    """
    sa = sample_every(a.coords, a.cum_km, SIMILARITY_SAMPLE_KM)
    sb = sample_every(b.coords, b.cum_km, SIMILARITY_SAMPLE_KM)
    return max(_coverage(sa, sb), _coverage(sb, sa))


def detour_via_points(base: RouteOption) -> list[list[LatLon]]:
    """Two rounds of via-points offset perpendicular to the base route.

    Round 1 tries both sides of the midpoint plus one point at a third and one
    at two thirds of the route; round 2 tries the remaining thirds and a doubled
    offset at the midpoint. Each round is routed in parallel and the second
    round only runs when the first did not yield enough distinct routes.
    """
    total = base.distance_km
    offset = min(max(DETOUR_OFFSET_FRACTION * total, DETOUR_OFFSET_MIN_KM), DETOUR_OFFSET_MAX_KM)
    rounds = [
        [(0.5, offset), (0.5, -offset), (0.33, -offset), (0.67, offset)],
        [(0.33, offset), (0.67, -offset), (0.5, 2 * offset), (0.5, -2 * offset)],
    ]
    out: list[list[LatLon]] = []
    for spec in rounds:
        vias: list[LatLon] = []
        for frac, off in spec:
            at = frac * total
            point, _, _ = locate_along(base.coords, base.cum_km, at)
            before, _, _ = locate_along(base.coords, base.cum_km, max(at - 5.0, 0.0))
            after, _, _ = locate_along(base.coords, base.cum_km, min(at + 5.0, total))
            heading = initial_bearing_deg(before, after)
            vias.append(destination_point(point, heading + (90 if off > 0 else -90), abs(off)))
        out.append(vias)
    return out


def _safe_route(router: OSRMRouter, waypoints: list[LatLon]) -> Optional[RouteOption]:
    try:
        routes = router.route(waypoints, alternatives=1, source="osrm-detour")
    except RoutingError as exc:
        log.info("Detour candidate failed: %s", exc)
        return None
    return routes[0] if routes else None


def fetch_route_options(
    origin: LatLon, destination: LatLon, want: int | None = None, router: OSRMRouter | None = None
) -> list[RouteOption]:
    """Up to ``want`` distinct route options, fastest first."""
    want = want or settings.TRUCK_ROUTING["ROUTE_OPTIONS"]
    router = router or OSRMRouter()

    primary = router.route([origin, destination], alternatives=want)
    if not primary:
        raise RoutingError(
            "No drivable route was found between these locations.", status_code=400, code="no_route"
        )

    options: list[RouteOption] = []
    for candidate in sorted(primary, key=lambda r: r.duration_s):
        if all(route_similarity(candidate, kept) <= MAX_SIMILARITY_PROVIDER for kept in options):
            options.append(candidate)

    provider_count = len(options)
    base = options[0]
    rounds_used = 0
    for vias in detour_via_points(base):
        if len(options) >= want:
            break
        rounds_used += 1
        with ThreadPoolExecutor(max_workers=len(vias)) as pool:
            futures = [pool.submit(_safe_route, router, [origin, via, destination]) for via in vias]
            candidates = [f.result() for f in futures]
        for cand in sorted((c for c in candidates if c is not None), key=lambda r: r.duration_s):
            if len(options) >= want:
                break
            if cand.duration_s > base.duration_s * MAX_DETOUR_DURATION_FACTOR:
                continue
            if any(route_similarity(cand, kept) > MAX_SIMILARITY_DETOUR for kept in options):
                continue
            options.append(cand)

    log.info(
        "Route options: %d from provider (%d returned), %d synthesized in %d detour round(s)",
        provider_count, len(primary), len(options) - provider_count, rounds_used,
    )
    return sorted(options[:want], key=lambda r: r.duration_s)
