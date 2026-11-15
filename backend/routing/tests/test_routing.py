import math

import pytest

from routing.services import routing
from routing.services.domain import RouteOption, miles_to_km
from routing.services.geo import KM_PER_DEG_LAT, cumulative_km, haversine_km

from .helpers import make_route


def _osrm_payload():
    coords = [[-105.0, 40.0], [-104.5, 40.0], [-104.0, 40.0]]
    seg = haversine_km((40.0, -105.0), (40.0, -104.5)) * 1000
    return {
        "distance": seg * 2,
        "duration": 3600.0,
        "geometry": {"type": "LineString", "coordinates": coords},
        "legs": [{
            "annotation": {"distance": [seg, seg], "duration": [1200.0, 2400.0]},
            "steps": [
                {"ref": "I 80", "name": "Dwight D. Eisenhower Highway", "distance": seg * 1.5},
                {"ref": "US 287; US 30", "name": "", "distance": seg * 0.5},
                {"name": "Main Street", "distance": 50},
            ],
        }],
    }


def test_parse_osrm_route_uses_annotations_for_time_profile():
    option = routing.parse_osrm_route(_osrm_payload())
    assert len(option.coords) == 3
    assert option.coords[0] == (40.0, -105.0)
    assert option.duration_s == pytest.approx(3600)
    assert option.cum_s[1] == pytest.approx(1200)  # first half is faster than the second
    assert option.cum_km[1] == pytest.approx(option.distance_km / 2)
    assert option.major_roads == ["I-80", "US-287"]


def test_parse_osrm_route_applies_truck_duration_factor():
    option = routing.parse_osrm_route(_osrm_payload(), duration_factor=1.2)
    assert option.duration_s == pytest.approx(4320)
    assert option.cum_s[1] == pytest.approx(1440)


def test_parse_osrm_route_falls_back_without_annotations():
    payload = _osrm_payload()
    payload["legs"][0].pop("annotation")
    option = routing.parse_osrm_route(payload)
    assert option.duration_s == pytest.approx(3600)
    assert option.cum_s[1] == pytest.approx(1800)


def test_route_similarity_identical_and_distinct():
    a = make_route(miles=200, lat=40.0)
    b = make_route(miles=200, lat=40.0)
    c = make_route(miles=200, lat=40.5)  # ~55 km north
    assert routing.route_similarity(a, b) == pytest.approx(1.0)
    assert routing.route_similarity(a, c) < 0.05


def test_route_similarity_detects_spur_duplicates():
    base = make_route(miles=200)
    spur_coords = base.coords + [(base.coords[-1][0] + 0.2, base.coords[-1][1])]
    cum_km = cumulative_km(spur_coords)
    spur = RouteOption(coords=spur_coords, cum_km=cum_km, cum_s=[c * 60 for c in cum_km], source="x")
    assert routing.route_similarity(base, spur) > 0.9


class FakeRouter:
    """Returns one straight route for A->B and a straight A->via->B polyline for via requests."""

    def __init__(self, alternatives=1):
        self.alternatives = alternatives
        self.calls = []

    def route(self, waypoints, alternatives=1, source="osrm"):
        self.calls.append(list(waypoints))
        if len(waypoints) == 2:
            routes = [make_route(miles=300, lat=40.0)]
            if self.alternatives > 1:
                routes.append(make_route(miles=310, mph=48, lat=40.4))
            return routes
        coords = []
        for a, b in zip(waypoints, waypoints[1:]):
            coords.extend([(a[0] + (b[0] - a[0]) * t / 50, a[1] + (b[1] - a[1]) * t / 50) for t in range(50)])
        coords.append(waypoints[-1])
        cum_km = cumulative_km(coords)
        cum_s = [c / miles_to_km(50) * 3600 for c in cum_km]
        return [RouteOption(coords=coords, cum_km=cum_km, cum_s=cum_s, source=source)]


def test_fetch_route_options_synthesizes_detours_to_reach_three():
    router = FakeRouter(alternatives=1)
    base = make_route(miles=300, lat=40.0)
    options = routing.fetch_route_options(base.coords[0], base.coords[-1], want=3, router=router)
    assert len(options) == 3
    assert options[0].source == "osrm"
    assert {o.source for o in options[1:]} == {"osrm-detour"}
    assert options[0].duration_s <= options[1].duration_s <= options[2].duration_s
    for detour in options[1:]:
        assert routing.route_similarity(options[0], detour) <= routing.MAX_SIMILARITY_DETOUR
        assert detour.duration_s <= options[0].duration_s * routing.MAX_DETOUR_DURATION_FACTOR
    # Only the first round (four via-points, routed in parallel) was needed.
    assert len(router.calls) == 5


def test_fetch_route_options_keeps_provider_alternatives_first():
    router = FakeRouter(alternatives=2)
    base = make_route(miles=300, lat=40.0)
    options = routing.fetch_route_options(base.coords[0], base.coords[-1], want=3, router=router)
    assert len(options) == 3
    assert [o.source for o in options].count("osrm") == 2


def test_detour_via_points_are_perpendicular_offsets():
    base = make_route(miles=300, lat=40.0)
    rounds = routing.detour_via_points(base)
    assert len(rounds) == 2
    assert all(len(vias) == 4 for vias in rounds)
    expected_offset = min(
        max(routing.DETOUR_OFFSET_FRACTION * base.distance_km, routing.DETOUR_OFFSET_MIN_KM),
        routing.DETOUR_OFFSET_MAX_KM,
    )
    mid = base.coords[len(base.coords) // 2]
    north, south = rounds[0][0], rounds[0][1]
    for via in (north, south):
        assert haversine_km(mid, via) == pytest.approx(expected_offset, rel=0.02)
    assert (north[0] - 40.0) * (south[0] - 40.0) < 0  # opposite sides of the route
    far = rounds[1][2]
    assert haversine_km(mid, far) == pytest.approx(2 * expected_offset, rel=0.02)
