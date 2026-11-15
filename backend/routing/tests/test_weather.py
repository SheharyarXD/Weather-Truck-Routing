import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from routing.services.weather import OpenMeteoClient, parse_series

T0 = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)


def _payload(hours=3, wind=(10, 20, 30), rain=(0.0, 0.2, 0.0), snow=(0.0, 0.0, 1.5)):
    return {
        "hourly": {
            "time": [(T0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)],
            "temperature_2m": [30.0, 32.0, 34.0][:hours],
            "wind_speed_10m": list(wind)[:hours],
            "wind_gusts_10m": [w * 1.5 for w in wind][:hours],
            "rain": list(rain)[:hours],
            "showers": [0.05] * hours,
            "snowfall": list(snow)[:hours],
            "weather_code": [1, 61, None][:hours],
        }
    }


def test_parse_series_combines_rain_and_showers():
    series = parse_series(_payload(), 40.0, -105.0)
    assert len(series) == 3
    assert series.rain_in_hr == pytest.approx([0.05, 0.25, 0.05])
    assert series.weather_code == [1, 61, None]
    assert series.times[0] == T0


def test_sample_at_interpolates_wind_and_uses_hour_bucket_for_precipitation():
    series = parse_series(_payload(), 40.0, -105.0)
    sample = series.sample_at(T0 + timedelta(minutes=30))
    assert sample.wind_mph == pytest.approx(15.0)
    assert sample.temp_f == pytest.approx(31.0)
    assert sample.rain_in_hr == pytest.approx(0.05)  # hour 0 bucket
    assert sample.time == T0
    later = series.sample_at(T0 + timedelta(hours=1, minutes=45))
    assert later.wind_mph == pytest.approx(27.5)
    assert later.rain_in_hr == pytest.approx(0.25)
    assert later.description == "Light rain"


def test_sample_at_clamps_outside_the_series():
    series = parse_series(_payload(), 40.0, -105.0)
    assert series.sample_at(T0 - timedelta(hours=5)).wind_mph == 10
    assert series.sample_at(T0 + timedelta(hours=9)).wind_mph == 30
    assert series.sample_at(T0 + timedelta(hours=9)).description == "Unknown"


@responses.activate
def test_client_batches_requests_preserves_order_and_caches():
    seen = []

    def callback(request):
        query = parse_qs(urlparse(request.url).query)
        lats = query["latitude"][0].split(",")
        seen.append(len(lats))
        assert query["wind_speed_unit"] == ["mph"]
        assert query["precipitation_unit"] == ["inch"]
        assert query["start_hour"] == ["2030-01-01T12:00"]
        assert query["end_hour"] == ["2030-01-01T15:00"]
        body = [dict(_payload(hours=4, wind=(float(lat), 0, 0, 0)), latitude=float(lat)) for lat in lats]
        return 200, {}, json.dumps(body)

    responses.add_callback(responses.GET, "https://api.open-meteo.com/v1/forecast", callback=callback)
    client = OpenMeteoClient(batch_size=50)
    points = [(30.0 + i * 0.1, -100.0) for i in range(130)]

    series = client.hourly(points, T0 + timedelta(minutes=10), T0 + timedelta(hours=2, minutes=30))
    assert sorted(seen) == [30, 50, 50]  # batches are fetched concurrently
    assert len(series) == 130
    # Output order matches input order even though batches complete in any order.
    assert [s.wind_mph[0] for s in series] == pytest.approx([round(p[0], 3) for p in points])

    client.hourly(points, T0 + timedelta(minutes=10), T0 + timedelta(hours=2, minutes=30))
    assert len(seen) == 3  # second call is served from cache
