import json
from datetime import datetime, timedelta, timezone

import pytest

from routing.services import planner
from routing.services.domain import Place

from .helpers import FakeWeather, make_route


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type="application/json")


def _departure(hours_ahead=6):
    return (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).replace(microsecond=0).isoformat()


@pytest.fixture
def fake_services(monkeypatch):
    """Replace the three external services with deterministic fakes."""
    places = {
        "Denver, CO": Place("Denver, Colorado, United States", 40.0, -105.0),
        "Cheyenne, WY": Place("Cheyenne, Wyoming, United States", 40.0, -102.0),
    }
    monkeypatch.setattr(planner, "geocode", lambda q: places[q])

    routes = [
        make_route(miles=100, mph=50, lat=40.0),  # calm, 2h00
        make_route(miles=90, mph=60, lat=40.5),  # fastest, but windy (see FakeWeather below)
        make_route(miles=110, mph=50, lat=39.5),  # calm, 2h12
    ]
    monkeypatch.setattr(planner, "fetch_route_options", lambda o, d, want=3: routes)

    weather = FakeWeather(wind=lambda lat, lon, hour: 50.0 if lat > 40.25 else 8.0)
    monkeypatch.setattr(planner, "OpenMeteoClient", lambda: weather)
    return weather


def test_health(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_plan_returns_ranked_routes_with_weather_and_recommendation(client, fake_services):
    body = {
        "origin": "Denver, CO",
        "destination": "Cheyenne, WY",
        "departure_time": _departure(),
        "load_weight_lb": 35000,
        "sample_interval_miles": 25,
    }
    response = _post(client, "/api/plan/", body)
    assert response.status_code == 200, response.content
    data = response.json()

    assert data["origin"]["label"].startswith("Denver")
    assert len(data["routes"]) == 3
    assert [r["name"] for r in data["routes"]] == ["Route A", "Route B", "Route C"]
    # Routes are named by speed: the 90-mile windy route is the fastest -> "Route A".
    fastest = data["routes"][0]
    assert fastest["distance_miles"] == 90
    assert fastest["summary"]["no_travel_miles"] == 90  # 50 mph wind with 35,000 lb -> No Travel
    assert fastest["rank"] == 3 and not fastest["recommended"]

    recommended = next(r for r in data["routes"] if r["recommended"])
    assert recommended["distance_miles"] == 100
    assert recommended["rank"] == 1
    assert data["recommendation"]["route_id"] == recommended["id"]
    assert data["recommendation"]["reasons"][0].startswith("Fewest No-Travel miles")
    assert data["recommendation"]["warning"] is None

    checkpoint = recommended["checkpoints"][1]
    assert checkpoint["mile"] == 25
    assert checkpoint["weather"]["wind_mph"] == 8
    assert checkpoint["risk"]["overall"] == "Low"
    assert len(checkpoint["path"]) >= 2
    assert recommended["checkpoints"][-1]["is_destination"]

    assert data["heatmap"]["hours"] == 48
    assert data["heatmap"]["start"].endswith(":00:00Z")
    assert 10 <= len(data["heatmap"]["points"]) <= 180
    assert fake_services.calls == 1  # one batched weather fetch for all checkpoints


def test_plan_accepts_coordinates_and_ten_mile_sampling(client, fake_services):
    body = {
        "origin": {"lat": 40.0, "lng": -105.0, "label": "Yard"},
        "destination": {"lat": 40.0, "lng": -102.0},
        "departure_time": _departure(),
        "load_weight_lb": 20000,
        "sample_interval_miles": 10,
    }
    response = _post(client, "/api/plan/", body)
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["origin"]["label"] == "Yard"
    assert len(data["routes"][1]["checkpoints"]) == 11  # 100 miles / 10 + destination


@pytest.mark.parametrize(
    "override,field",
    [
        ({"sample_interval_miles": 15}, "sample_interval_miles"),
        ({"departure_time": "2001-01-01T00:00:00Z"}, "departure_time"),
        ({"load_weight_lb": -5}, "load_weight_lb"),
        ({"origin": "x"}, "origin"),
    ],
)
def test_plan_validation_errors(client, fake_services, override, field):
    body = {
        "origin": "Denver, CO",
        "destination": "Cheyenne, WY",
        "departure_time": _departure(),
        "load_weight_lb": 35000,
        "sample_interval_miles": 25,
        **override,
    }
    response = _post(client, "/api/plan/", body)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in error["details"]


def test_plan_reports_geocoding_failures_as_json(client, fake_services, monkeypatch):
    from routing.exceptions import GeocodingError

    def failing(q):
        raise GeocodingError("Could not find a location for 'Nowhere'.", status_code=400)

    monkeypatch.setattr(planner, "geocode", failing)
    body = {"origin": "Nowhere", "destination": "Cheyenne, WY", "departure_time": _departure(),
            "load_weight_lb": 1000}
    response = _post(client, "/api/plan/", body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "geocoding_failed"


def test_heatmap_endpoint(client, fake_services):
    body = {
        "points": [[40.0, -105.0], [40.5, -104.0]],
        "start": _departure(),
        "hours": 48,
        "load_weight_lb": 35000,
    }
    response = _post(client, "/api/heatmap/", body)
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["hours"] == 48
    assert len(data["times"]) == 49
    assert len(data["points"]) == 2
    calm, windy = data["points"]
    assert len(calm["risk"]) == 49 and set(calm["risk"]) == {0}
    assert set(windy["risk"]) == {4}  # 50 mph wind + 35,000 lb -> No Travel
    assert windy["wind"][0] == 50


def test_geocode_endpoint(client, monkeypatch):
    from routing import views

    monkeypatch.setattr(views, "suggest", lambda q, limit: [Place("Denver, Colorado", 39.74, -104.98)])
    response = client.get("/api/geocode/?q=den")
    assert response.status_code == 200
    assert response.json()["results"][0]["label"] == "Denver, Colorado"
    assert client.get("/api/geocode/?q=d").status_code == 400


def test_spa_fallback_served_for_unknown_paths(client):
    response = client.get("/some/client/route")
    assert response.status_code == 200
    assert b"<html" in response.content.lower()
