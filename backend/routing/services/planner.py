"""Orchestrates geocoding, routing, checkpoint sampling, weather, risk and ranking."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

from django.conf import settings

from ..exceptions import PlanningError
from .checkpoints import sample_checkpoints
from .corridor import corridor_grid
from .domain import LatLon, Place, PlannedRoute, iso_utc, km_to_miles
from .geo import haversine_km, simplify
from .geocoding import geocode
from .risk import LEVELS, assess, assess_values
from .routing import fetch_route_options
from .summary import RANKING_CRITERIA, explain_recommendation, rank_routes, summarize
from .weather import OpenMeteoClient, floor_hour

log = logging.getLogger(__name__)

ROUTE_SIMPLIFY_TOLERANCE_DEG = 0.0006  # ~65 m: the overview line drawn for non-selected routes


@dataclass
class PlanRequest:
    origin: Union[str, Place]
    destination: Union[str, Place]
    departure: datetime
    load_lb: float
    interval_miles: float


def _resolve(place: Union[str, Place]) -> Place:
    return place if isinstance(place, Place) else geocode(place)


def plan_trip(req: PlanRequest) -> dict:
    cfg = settings.TRUCK_ROUTING
    started = time.perf_counter()
    timings: dict[str, float] = {}

    def lap(stage: str) -> None:
        timings[stage] = round(time.perf_counter() - started - sum(timings.values()), 2)

    departure = req.departure.astimezone(timezone.utc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        origin_future = pool.submit(_resolve, req.origin)
        destination_future = pool.submit(_resolve, req.destination)
        origin, destination = origin_future.result(), destination_future.result()
    lap("geocoding")

    straight_km = haversine_km((origin.lat, origin.lon), (destination.lat, destination.lon))
    if straight_km < 0.5:
        raise PlanningError("Origin and destination are the same place.")
    if km_to_miles(straight_km) > cfg["MAX_TRIP_MILES"]:
        raise PlanningError(f"Trips longer than {cfg['MAX_TRIP_MILES']:.0f} miles are not supported.")

    options = fetch_route_options(
        (origin.lat, origin.lon), (destination.lat, destination.lon), want=cfg["ROUTE_OPTIONS"]
    )
    lap("routing")

    routes: list[PlannedRoute] = []
    for i, option in enumerate(sorted(options, key=lambda o: o.duration_s)):
        letter = chr(ord("A") + i)
        routes.append(
            PlannedRoute(
                id=letter,
                name=f"Route {letter}",
                option=option,
                departure=departure,
                checkpoints=sample_checkpoints(option, req.interval_miles, departure),
                geometry=simplify(option.coords, ROUTE_SIMPLIFY_TOLERANCE_DEG),
            )
        )

    lap("checkpoints")

    _attach_weather(routes, req.load_lb)
    lap("weather")

    for route in routes:
        route.summary = summarize(route.checkpoints)
    ranked = rank_routes(routes)
    reasons, warning = explain_recommendation(ranked)

    heatmap_points = corridor_grid(
        [route.geometry for route in routes], cfg["HEATMAP_CORRIDOR_MILES"], cfg["HEATMAP_MAX_POINTS"]
    )
    lap("ranking_and_grid")

    total = round(time.perf_counter() - started, 2)
    log.info(
        "Planned %s -> %s: %d routes, %d checkpoints in %.1fs %s",
        origin.label, destination.label, len(routes),
        sum(len(r.checkpoints) for r in routes), total, timings,
    )
    return {
        "timing_seconds": {**timings, "total": total},
        "origin": origin.to_dict(),
        "destination": destination.to_dict(),
        "departure_time": iso_utc(departure),
        "load_weight_lb": req.load_lb,
        "sample_interval_miles": req.interval_miles,
        "routes": [route.to_dict() for route in routes],
        "recommendation": {
            "route_id": ranked[0].id,
            "reasons": reasons,
            "warning": warning,
            "criteria": RANKING_CRITERIA,
        },
        "risk_levels": list(LEVELS),
        "heatmap": {
            "start": iso_utc(floor_hour(departure)),
            "hours": cfg["HEATMAP_HOURS"],
            "points": [[lat, lon] for lat, lon in heatmap_points],
        },
        "generated_at": iso_utc(datetime.now(timezone.utc)),
    }


def _attach_weather(routes: list[PlannedRoute], load_lb: float) -> None:
    """Fetch forecasts for every checkpoint and evaluate risk at the truck's ETA."""
    points = [(cp.lat, cp.lon) for route in routes for cp in route.checkpoints]
    if not points:
        return
    departure = routes[0].departure
    latest_eta = max(cp.eta for route in routes for cp in route.checkpoints)
    series = OpenMeteoClient().hourly(points, departure, latest_eta + timedelta(hours=1))

    k = 0
    for route in routes:
        for cp in route.checkpoints:
            sample = series[k].sample_at(cp.eta)
            k += 1
            cp.weather = sample
            cp.risk = assess(sample, load_lb)


def heatmap(points: Sequence[LatLon], start: datetime, hours: int, load_lb: float) -> dict:
    """Hourly weather + risk for a set of corridor points over ``hours`` hours from ``start``."""
    start_hour = floor_hour(start)
    series = OpenMeteoClient().hourly(points, start_hour, start_hour + timedelta(hours=hours))
    n = min(len(s) for s in series) if series else 0
    times = series[0].times[:n] if series else []
    out = []
    for s in series:
        out.append({
            "lat": s.lat,
            "lng": s.lon,
            "risk": [
                assess_values(s.wind_mph[i], s.rain_in_hr[i], s.snow_in_hr[i], load_lb).score
                for i in range(n)
            ],
            "wind": [round(v, 1) for v in s.wind_mph[:n]],
            "gust": [round(v, 1) for v in s.gust_mph[:n]],
            "rain": [round(v, 3) for v in s.rain_in_hr[:n]],
            "snow": [round(v, 2) for v in s.snow_in_hr[:n]],
            "temp": [round(v, 1) for v in s.temp_f[:n]],
        })
    return {
        "start": iso_utc(start_hour),
        "hours": max(n - 1, 0),
        "times": [iso_utc(t) for t in times],
        "load_weight_lb": load_lb,
        "points": out,
    }
