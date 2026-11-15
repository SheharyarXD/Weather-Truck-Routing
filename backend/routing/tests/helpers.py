"""Synthetic fixtures shared by the test modules."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from routing.services.domain import Checkpoint, PlannedRoute, RouteOption, miles_to_km
from routing.services.geo import KM_PER_DEG_LAT, cumulative_km
from routing.services.risk import SCORES, RiskAssessment
from routing.services.weather import HourlySeries, ceil_hour, floor_hour

DEPARTURE = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)


def make_route(miles: float = 100.0, mph: float = 50.0, *, lat: float = 40.0, lon0: float = -105.0,
               n: int = 201, source: str = "osrm") -> RouteOption:
    """A straight east-west route at constant speed."""
    km = miles_to_km(miles)
    deg = km / (KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    coords = [(lat, lon0 + deg * i / (n - 1)) for i in range(n)]
    cum_km = cumulative_km(coords)
    scale = km / cum_km[-1]
    cum_km = [c * scale for c in cum_km]
    speed_kmh = miles_to_km(mph)
    cum_s = [c / speed_kmh * 3600.0 for c in cum_km]
    return RouteOption(coords=coords, cum_km=cum_km, cum_s=cum_s, source=source, major_roads=["I-70"])


def risk(level: str) -> RiskAssessment:
    return RiskAssessment(wind=level, rain="Low", snow="Low", overall=level, score=SCORES[level],
                          factors=(f"Wind: {level}",))


def planned_route(route_id: str, segments: list[tuple[str, float]], mph: float = 50.0) -> PlannedRoute:
    """Route whose checkpoints carry the given ``(level, miles)`` segments."""
    checkpoints = []
    mile = 0.0
    for i, (level, miles) in enumerate(segments):
        checkpoints.append(Checkpoint(index=i, mile=mile, segment_miles=miles, lat=40.0, lon=-105.0 + i,
                                      eta=DEPARTURE + timedelta(hours=mile / mph),
                                      hours_from_departure=mile / mph, path=[], risk=risk(level)))
        mile += miles
    checkpoints.append(Checkpoint(index=len(segments), mile=mile, segment_miles=0.0, lat=40.0,
                                  lon=-100.0, eta=DEPARTURE + timedelta(hours=mile / mph),
                                  hours_from_departure=mile / mph, path=[], is_destination=True,
                                  risk=risk("Low")))
    option = make_route(mile, mph)
    return PlannedRoute(id=route_id, name=f"Route {route_id}", option=option, departure=DEPARTURE,
                        checkpoints=checkpoints, geometry=option.coords)


class FakeWeather:
    """Stand-in for ``OpenMeteoClient`` producing deterministic series."""

    def __init__(self, wind=lambda lat, lon, hour: 5.0, rain=lambda lat, lon, hour: 0.0,
                 snow=lambda lat, lon, hour: 0.0):
        self.wind, self.rain, self.snow = wind, rain, snow
        self.calls = 0

    def hourly(self, points, start, end):
        self.calls += 1
        start = floor_hour(start)
        end = max(ceil_hour(end), start + timedelta(hours=1))
        n = int((end - start).total_seconds() // 3600) + 1
        times = [start + timedelta(hours=i) for i in range(n)]
        out = []
        for lat, lon in points:
            out.append(HourlySeries(
                lat=lat, lon=lon, times=times,
                temp_f=[50.0] * n,
                wind_mph=[self.wind(lat, lon, i) for i in range(n)],
                gust_mph=[self.wind(lat, lon, i) * 1.3 for i in range(n)],
                rain_in_hr=[self.rain(lat, lon, i) for i in range(n)],
                snow_in_hr=[self.snow(lat, lon, i) for i in range(n)],
                weather_code=[1] * n,
            ))
        return out
