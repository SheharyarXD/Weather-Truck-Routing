"""Sample a route every N miles and compute the truck's ETA at each checkpoint."""
from __future__ import annotations

from datetime import datetime, timedelta

from .domain import Checkpoint, RouteOption, km_to_miles, miles_to_km
from .geo import interpolate, locate_along, simplify

PATH_SIMPLIFY_TOLERANCE_DEG = 0.0004  # ~45 m: plenty for drawing, keeps payloads small
END_MERGE_FRACTION = 0.1


def checkpoint_marks_km(total_km: float, interval_km: float) -> list[float]:
    """Cumulative distances to sample: ``0, I, 2I, ...`` plus the destination.

    A regular mark that lands within 10% of an interval of the destination is
    dropped so the trip does not end with a near-duplicate checkpoint.
    """
    if total_km <= 0:
        return [0.0]
    marks = [k * interval_km for k in range(int(total_km // interval_km) + 1)]
    if len(marks) > 1 and total_km - marks[-1] < END_MERGE_FRACTION * interval_km:
        marks.pop()
    if marks[-1] < total_km:
        marks.append(total_km)
    return marks


def sample_checkpoints(route: RouteOption, interval_miles: float, departure: datetime) -> list[Checkpoint]:
    """Checkpoints along ``route`` with ETAs derived from the route's time profile.

    Each checkpoint "owns" the stretch of road up to the next checkpoint
    (``segment_miles``); its weather is evaluated at the truck's ETA there.
    """
    interval_km = miles_to_km(interval_miles)
    marks = checkpoint_marks_km(route.distance_km, interval_km)
    located = [locate_along(route.coords, route.cum_km, mark) for mark in marks]

    checkpoints: list[Checkpoint] = []
    last = len(marks) - 1
    for k, (mark, (point, idx, frac)) in enumerate(zip(marks, located)):
        seconds = interpolate(route.cum_s, idx, frac)
        if k == last:
            path = [point]
            segment_miles = 0.0
        else:
            next_point, next_idx, _ = located[k + 1]
            path = simplify([point, *route.coords[idx + 1:next_idx + 1], next_point], PATH_SIMPLIFY_TOLERANCE_DEG)
            segment_miles = km_to_miles(marks[k + 1] - mark)
        checkpoints.append(
            Checkpoint(
                index=k,
                mile=km_to_miles(mark),
                segment_miles=segment_miles,
                lat=point[0],
                lon=point[1],
                eta=departure + timedelta(seconds=seconds),
                hours_from_departure=seconds / 3600.0,
                path=path,
                is_destination=(k == last),
            )
        )
    return checkpoints
