from datetime import timedelta

import pytest

from routing.services.checkpoints import checkpoint_marks_km, sample_checkpoints
from routing.services.domain import km_to_miles, miles_to_km

from .helpers import DEPARTURE, make_route


@pytest.mark.parametrize(
    "total_miles,interval,expected",
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (101, 25, [0, 25, 50, 75, 101]),  # the mile-100 mark merges into the destination
        (60, 25, [0, 25, 50, 60]),
        (5, 10, [0, 5]),
        (0, 10, [0]),
    ],
)
def test_checkpoint_marks(total_miles, interval, expected):
    marks = checkpoint_marks_km(miles_to_km(total_miles), miles_to_km(interval))
    assert [round(km_to_miles(m), 6) for m in marks] == pytest.approx(expected)


def test_checkpoints_have_correct_miles_etas_and_segments():
    route = make_route(miles=100, mph=50)
    checkpoints = sample_checkpoints(route, 25, DEPARTURE)

    assert [round(cp.mile) for cp in checkpoints] == [0, 25, 50, 75, 100]
    assert [cp.hours_from_departure for cp in checkpoints] == pytest.approx([0, 0.5, 1.0, 1.5, 2.0], abs=1e-6)
    assert checkpoints[1].eta == DEPARTURE + timedelta(minutes=30)
    assert [round(cp.segment_miles, 6) for cp in checkpoints] == pytest.approx([25, 25, 25, 25, 0])
    assert checkpoints[-1].is_destination and not checkpoints[0].is_destination
    assert sum(cp.segment_miles for cp in checkpoints) == pytest.approx(route.distance_miles)


def test_checkpoint_paths_are_continuous():
    route = make_route(miles=100, mph=50)
    checkpoints = sample_checkpoints(route, 25, DEPARTURE)
    for current, following in zip(checkpoints, checkpoints[1:]):
        assert current.path[0] == pytest.approx((current.lat, current.lon))
        assert current.path[-1] == pytest.approx((following.lat, following.lon))
    assert checkpoints[-1].path == [(checkpoints[-1].lat, checkpoints[-1].lon)]


def test_checkpoints_respect_variable_speed_profile():
    route = make_route(miles=100, mph=50)
    # Make the second half of the trip twice as slow.
    half = len(route.cum_s) // 2
    route.cum_s = [s if i <= half else route.cum_s[half] + (s - route.cum_s[half]) * 2
                   for i, s in enumerate(route.cum_s)]
    checkpoints = sample_checkpoints(route, 50, DEPARTURE)
    assert checkpoints[1].hours_from_departure == pytest.approx(1.0, abs=0.02)
    assert checkpoints[2].hours_from_departure == pytest.approx(3.0, abs=0.02)
