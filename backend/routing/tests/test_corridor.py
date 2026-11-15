from routing.services.corridor import corridor_grid
from routing.services.domain import miles_to_km
from routing.services.geo import SpatialIndex, fast_distance_km

from .helpers import make_route


def _nearest_km(point, coords):
    return min(fast_distance_km(point, c) for c in coords)


def test_grid_respects_budget_and_stays_inside_corridor():
    route = make_route(miles=600)
    grid = corridor_grid([route.coords], radius_miles=40, max_points=180)
    assert 40 <= len(grid) <= 180
    radius_km = miles_to_km(40)
    assert all(_nearest_km(p, route.coords) <= radius_km * 1.02 for p in grid)


def test_grid_covers_the_whole_route():
    route = make_route(miles=600)
    grid = corridor_grid([route.coords], radius_miles=40, max_points=180)
    index = SpatialIndex(grid, cell_km=30)
    # Every part of the route should have a sample point reasonably close by.
    assert all(index.has_within(c, 45) for c in route.coords[::10])


def test_short_trip_gets_a_dense_grid():
    short = make_route(miles=40)
    long = make_route(miles=1500)
    assert len(corridor_grid([short.coords], 40, 180)) >= 20
    assert len(corridor_grid([long.coords], 40, 180)) <= 180


def test_multiple_routes_share_one_grid():
    a = make_route(miles=300, lat=40.0)
    b = make_route(miles=300, lat=40.6)
    grid = corridor_grid([a.coords, b.coords], 40, 180)
    lats = [p[0] for p in grid]
    assert min(lats) < 40.0 and max(lats) > 40.6
    assert len(grid) <= 180
