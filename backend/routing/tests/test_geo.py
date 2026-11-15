import math

import pytest

from routing.services import geo


def test_haversine_denver_to_salt_lake_city():
    distance = geo.haversine_km((39.7392, -104.9903), (40.7608, -111.8910))
    assert 590 < distance < 605


def test_fast_distance_matches_haversine_for_short_distances():
    a, b = (40.0, -105.0), (40.3, -105.4)
    assert geo.fast_distance_km(a, b) == pytest.approx(geo.haversine_km(a, b), rel=0.005)


def test_destination_point_round_trip():
    start = (40.0, -105.0)
    target = geo.destination_point(start, 90, 50)
    assert geo.haversine_km(start, target) == pytest.approx(50, abs=0.05)
    assert geo.initial_bearing_deg(start, target) == pytest.approx(90, abs=0.5)


def test_locate_along_interpolates_and_clamps():
    coords = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cum = geo.cumulative_km(coords)
    point, idx, frac = geo.locate_along(coords, cum, cum[-1] / 2)
    assert point == pytest.approx((0.0, 1.0), abs=1e-6)
    assert geo.locate_along(coords, cum, -5)[0] == coords[0]
    assert geo.locate_along(coords, cum, cum[-1] + 5)[0] == coords[-1]
    quarter, idx, frac = geo.locate_along(coords, cum, cum[-1] / 4)
    assert idx == 0 and frac == pytest.approx(0.5, abs=1e-6)
    assert quarter[1] == pytest.approx(0.5, abs=1e-6)


def test_sample_every_includes_both_ends():
    coords = [(0.0, 0.0), (0.0, 1.0)]
    cum = geo.cumulative_km(coords)
    samples = geo.sample_every(coords, cum, 20.0)
    assert samples[0] == coords[0]
    assert samples[-1] == coords[-1]
    assert len(samples) == math.ceil(cum[-1] / 20.0) + 1


def test_simplify_removes_collinear_points_and_keeps_corners():
    straight = [(40.0, -105.0 + i * 0.01) for i in range(100)]
    assert geo.simplify(straight, 1e-6) == [straight[0], straight[-1]]
    zigzag = [(40.0, -105.0), (40.5, -104.5), (40.0, -104.0), (40.5, -103.5)]
    assert geo.simplify(zigzag, 0.01) == zigzag


def test_spatial_index_membership():
    points = [(40.0, -105.0), (41.0, -106.0)]
    index = geo.SpatialIndex(points, cell_km=5)
    assert index.has_within((40.01, -105.01), 5)
    assert not index.has_within((40.5, -105.5), 5)
    assert index.min_distance_km((40.0, -105.0), 5) == pytest.approx(0.0)
