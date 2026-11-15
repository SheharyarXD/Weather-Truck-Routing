"""Open-Meteo client returning hourly series for many points, with batching and caching."""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import requests
from django.conf import settings
from django.core.cache import cache

from ..exceptions import WeatherError
from .domain import LatLon, WeatherSample
from .http import get_session, timeout

log = logging.getLogger(__name__)

HOURLY_VARS: tuple[str, ...] = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "weather_code",
)

WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Violent showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def describe_code(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"
    return WMO_DESCRIPTIONS.get(int(code), f"Weather code {code}")


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def ceil_hour(dt: datetime) -> datetime:
    floored = floor_hour(dt)
    return floored if floored == dt.astimezone(timezone.utc) else floored + timedelta(hours=1)


def _num(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) else default


@dataclass
class HourlySeries:
    lat: float
    lon: float
    times: list[datetime]
    temp_f: list[float]
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in_hr: list[float]
    snow_in_hr: list[float]
    weather_code: list[Optional[int]]

    def __len__(self) -> int:
        return len(self.times)

    def sample_index(self, i: int) -> WeatherSample:
        return WeatherSample(
            time=self.times[i],
            temp_f=self.temp_f[i],
            wind_mph=self.wind_mph[i],
            gust_mph=self.gust_mph[i],
            rain_in_hr=self.rain_in_hr[i],
            snow_in_hr=self.snow_in_hr[i],
            weather_code=self.weather_code[i],
            description=describe_code(self.weather_code[i]),
        )

    def sample_at(self, when: datetime) -> WeatherSample:
        """Weather at an arbitrary instant.

        Wind, gusts and temperature are interpolated linearly between the two
        surrounding forecast hours. Precipitation rates and the weather code
        come from the forecast hour containing ``when`` (they describe that
        whole hour). Instants outside the series are clamped to its ends.
        """
        when = when.astimezone(timezone.utc)
        n = len(self.times)
        if n == 1 or when <= self.times[0]:
            return self.sample_index(0)
        if when >= self.times[-1]:
            return self.sample_index(n - 1)
        i = int((when - self.times[0]).total_seconds() // 3600)
        i = max(0, min(i, n - 2))
        span = (self.times[i + 1] - self.times[i]).total_seconds()
        frac = (when - self.times[i]).total_seconds() / span if span > 0 else 0.0

        def lerp(values: list[float]) -> float:
            return values[i] + (values[i + 1] - values[i]) * frac

        return WeatherSample(
            time=self.times[i],
            temp_f=lerp(self.temp_f),
            wind_mph=lerp(self.wind_mph),
            gust_mph=lerp(self.gust_mph),
            rain_in_hr=self.rain_in_hr[i],
            snow_in_hr=self.snow_in_hr[i],
            weather_code=self.weather_code[i],
            description=describe_code(self.weather_code[i]),
        )


def parse_series(item: dict, lat: float, lon: float) -> HourlySeries:
    hourly = item.get("hourly") or {}
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly.get("time", [])]
    n = len(times)

    def column(name: str) -> list[float]:
        values = hourly.get(name) or []
        return [_num(values[i]) if i < len(values) else 0.0 for i in range(n)]

    rain = column("rain")
    showers = column("showers")
    codes_raw = hourly.get("weather_code") or []
    codes = [
        int(codes_raw[i]) if i < len(codes_raw) and codes_raw[i] is not None else None
        for i in range(n)
    ]
    return HourlySeries(
        lat=lat,
        lon=lon,
        times=times,
        temp_f=column("temperature_2m"),
        wind_mph=column("wind_speed_10m"),
        gust_mph=column("wind_gusts_10m"),
        rain_in_hr=[r + s for r, s in zip(rain, showers)],
        snow_in_hr=column("snowfall"),
        weather_code=codes,
    )


class OpenMeteoClient:
    def __init__(
        self, base_url: str | None = None, batch_size: int | None = None, max_workers: int = 4
    ) -> None:
        cfg = settings.TRUCK_ROUTING
        self.base_url = base_url or cfg["OPEN_METEO_URL"]
        self.batch_size = batch_size or cfg["WEATHER_BATCH_SIZE"]
        self.max_workers = max_workers
        self.cache_seconds = cfg["WEATHER_CACHE_SECONDS"]

    def hourly(self, points: Sequence[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        """Hourly forecasts for every point between ``start`` and ``end`` (inclusive, UTC)."""
        if not points:
            return []
        start_hour = floor_hour(start)
        end_hour = max(ceil_hour(end), start_hour + timedelta(hours=1))
        rounded = [(round(lat, 3), round(lon, 3)) for lat, lon in points]
        batches = [rounded[i:i + self.batch_size] for i in range(0, len(rounded), self.batch_size)]
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(batches))) as pool:
            results = list(pool.map(lambda b: self._fetch_batch(b, start_hour, end_hour), batches))
        series = [s for batch in results for s in batch]
        if len(series) != len(points):
            raise WeatherError("Weather service returned an unexpected number of locations.")
        return series

    def _fetch_batch(
        self, batch: list[LatLon], start_hour: datetime, end_hour: datetime
    ) -> list[HourlySeries]:
        key_src = json.dumps([batch, start_hour.isoformat(), end_hour.isoformat(), HOURLY_VARS])
        key = "wx:" + hashlib.sha1(key_src.encode()).hexdigest()
        cached = cache.get(key)
        if cached is not None:
            return cached

        params = {
            "latitude": ",".join(f"{lat:.3f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.3f}" for _, lon in batch),
            "hourly": ",".join(HOURLY_VARS),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "timezone": "UTC",
            "start_hour": start_hour.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end_hour.strftime("%Y-%m-%dT%H:%M"),
        }
        try:
            resp = get_session().get(self.base_url, params=params, timeout=timeout())
        except requests.RequestException as exc:
            raise WeatherError(f"Weather service unreachable: {exc}") from exc

        try:
            payload = resp.json()
        except ValueError as exc:
            raise WeatherError("Weather service returned an invalid response.") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise WeatherError(f"Weather service error: {payload.get('reason', 'unknown')}")
        if resp.status_code >= 400:
            raise WeatherError(f"Weather service error (HTTP {resp.status_code}).")

        items = payload if isinstance(payload, list) else [payload]
        if len(items) != len(batch):
            raise WeatherError("Weather service returned an unexpected number of locations.")
        series = [parse_series(item, lat, lon) for item, (lat, lon) in zip(items, batch)]
        cache.set(key, series, self.cache_seconds)
        return series
