"""Plain dataclasses shared by the routing services. No Django imports here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

LatLon = tuple[float, float]  # (latitude, longitude)

KM_PER_MILE = 1.609344


def km_to_miles(km: float) -> float:
    return km / KM_PER_MILE


def miles_to_km(miles: float) -> float:
    return miles * KM_PER_MILE


def iso_utc(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def to_dict(self) -> dict:
        return {"label": self.label, "lat": round(self.lat, 6), "lng": round(self.lon, 6)}


@dataclass
class RouteOption:
    """A drivable route with cumulative distance (km) and time (s) at every vertex."""

    coords: list[LatLon]
    cum_km: list[float]
    cum_s: list[float]
    source: str
    major_roads: list[str] = field(default_factory=list)

    @property
    def distance_km(self) -> float:
        return self.cum_km[-1]

    @property
    def distance_miles(self) -> float:
        return km_to_miles(self.cum_km[-1])

    @property
    def duration_s(self) -> float:
        return self.cum_s[-1]


@dataclass(frozen=True)
class WeatherSample:
    time: datetime
    temp_f: float
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    weather_code: Optional[int]
    description: str

    def to_dict(self) -> dict:
        return {
            "forecast_time": iso_utc(self.time),
            "temp_f": round(self.temp_f, 1),
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 2),
            "weather_code": self.weather_code,
            "description": self.description,
        }


@dataclass(frozen=True)
class RiskAssessment:
    wind: str
    rain: str
    snow: str
    overall: str
    score: int
    factors: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "wind": self.wind,
            "rain": self.rain,
            "snow": self.snow,
            "overall": self.overall,
            "score": self.score,
            "factors": list(self.factors),
        }


@dataclass
class Checkpoint:
    index: int
    mile: float
    segment_miles: float
    lat: float
    lon: float
    eta: datetime
    hours_from_departure: float
    path: list[LatLon]
    is_destination: bool = False
    weather: Optional[WeatherSample] = None
    risk: Optional[RiskAssessment] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "mile": round(self.mile, 1),
            "segment_miles": round(self.segment_miles, 1),
            "lat": round(self.lat, 5),
            "lng": round(self.lon, 5),
            "eta": iso_utc(self.eta),
            "hours_from_departure": round(self.hours_from_departure, 3),
            "is_destination": self.is_destination,
            "path": [[round(lat, 5), round(lon, 5)] for lat, lon in self.path],
            "weather": self.weather.to_dict() if self.weather else None,
            "risk": self.risk.to_dict() if self.risk else None,
        }


@dataclass
class RouteSummary:
    miles_by_level: dict[str, float]
    avg_risk: float
    max_level: str
    worst_checkpoint_index: Optional[int]

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level.get("No Travel", 0.0)

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level.get("Severe", 0.0)

    @property
    def high_miles(self) -> float:
        return self.miles_by_level.get("High", 0.0)

    @property
    def travelable(self) -> bool:
        return self.no_travel_miles <= 0

    def to_dict(self) -> dict:
        return {
            "miles_by_level": {k: round(v, 1) for k, v in self.miles_by_level.items()},
            "no_travel_miles": round(self.no_travel_miles, 1),
            "severe_miles": round(self.severe_miles, 1),
            "high_miles": round(self.high_miles, 1),
            "avg_risk": round(self.avg_risk, 2),
            "max_level": self.max_level,
            "worst_checkpoint_index": self.worst_checkpoint_index,
            "travelable": self.travelable,
        }


@dataclass
class PlannedRoute:
    id: str
    name: str
    option: RouteOption
    departure: datetime
    checkpoints: list[Checkpoint]
    geometry: list[LatLon]
    summary: Optional[RouteSummary] = None
    rank: int = 0
    recommended: bool = False

    @property
    def duration_s(self) -> float:
        return self.option.duration_s

    @property
    def arrival(self) -> datetime:
        return self.checkpoints[-1].eta

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.option.source,
            "major_roads": self.option.major_roads,
            "distance_miles": round(self.option.distance_miles, 1),
            "duration_seconds": round(self.option.duration_s),
            "departure_time": iso_utc(self.departure),
            "arrival_time": iso_utc(self.arrival),
            "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in self.geometry],
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
            "summary": self.summary.to_dict() if self.summary else None,
            "rank": self.rank,
            "recommended": self.recommended,
        }
