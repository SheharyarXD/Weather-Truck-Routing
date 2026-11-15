"""Per-route risk summaries, ranking and the human-readable recommendation."""
from __future__ import annotations

from typing import Callable

from .domain import Checkpoint, PlannedRoute, RouteSummary
from .risk import LEVELS, LOW

RANKING_CRITERIA = [
    "Fewest No-Travel miles",
    "Fewest Severe miles",
    "Fewest High miles",
    "Lowest average risk (distance-weighted)",
    "Shortest travel time",
]


def summarize(checkpoints: list[Checkpoint]) -> RouteSummary:
    """Miles per risk level and the distance-weighted average risk score.

    Each checkpoint's risk applies to the stretch it owns (``segment_miles``).
    The destination checkpoint owns no miles but still counts towards the
    route's maximum risk level.
    """
    miles = {level: 0.0 for level in LEVELS}
    weighted = 0.0
    total = 0.0
    worst_index: int | None = None
    worst_score = -1
    for cp in checkpoints:
        if cp.risk is None:
            continue
        miles[cp.risk.overall] += cp.segment_miles
        weighted += cp.risk.score * cp.segment_miles
        total += cp.segment_miles
        if cp.risk.score > worst_score:
            worst_score, worst_index = cp.risk.score, cp.index
    return RouteSummary(
        miles_by_level=miles,
        avg_risk=weighted / total if total > 0 else 0.0,
        max_level=LEVELS[worst_score] if worst_score >= 0 else LOW,
        worst_checkpoint_index=worst_index,
    )


def ranking_key(route: PlannedRoute) -> tuple:
    """Sort key implementing the brief's preference order.

    No-Travel miles are treated as worse than Severe miles and compared first.
    Values are rounded so floating-point noise cannot break genuine ties.
    """
    s = route.summary
    assert s is not None
    return (
        round(s.no_travel_miles, 1),
        round(s.severe_miles, 1),
        round(s.high_miles, 1),
        round(s.avg_risk, 2),
        round(route.duration_s),
    )


def rank_routes(routes: list[PlannedRoute]) -> list[PlannedRoute]:
    ranked = sorted(routes, key=ranking_key)
    for position, route in enumerate(ranked, start=1):
        route.rank = position
        route.recommended = position == 1
    return ranked


def format_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes} min"


def explain_recommendation(ranked: list[PlannedRoute]) -> tuple[list[str], str | None]:
    """Reasons why ``ranked[0]`` won, following the criteria in order, plus an optional warning."""
    best, others = ranked[0], ranked[1:]
    assert best.summary is not None
    reasons: list[str] = []

    def compare(fmt: Callable[[PlannedRoute], str]) -> str:
        return ", ".join(f"{r.name} {fmt(r)}" for r in others)

    if others:
        decided = False
        criteria = (
            ("no_travel_miles", "No-Travel miles"),
            ("severe_miles", "Severe-risk miles"),
            ("high_miles", "High-risk miles"),
        )
        for attr, label in criteria:
            values = [round(getattr(r.summary, attr), 1) for r in ranked]
            if len(set(values)) <= 1:
                if values[0] == 0:
                    if attr != "no_travel_miles":
                        reasons.append(f"No {label} on any route")
                else:
                    reasons.append(f"All routes have {values[0]:.0f} {label}")
                continue
            reasons.append(
                f"Fewest {label}: {values[0]:.0f} mi ({compare(lambda r: f'{getattr(r.summary, attr):.0f} mi')})"
            )
            decided = True
            break

        if not decided:
            averages = [round(r.summary.avg_risk, 2) for r in ranked]
            if len(set(averages)) > 1:
                reasons.append(
                    f"Lowest average risk: {averages[0]:.2f} ({compare(lambda r: f'{r.summary.avg_risk:.2f}')})"
                )
                decided = True
            else:
                reasons.append(f"Same average risk on every route ({averages[0]:.2f})")

        if not decided:
            reasons.append(
                f"Shortest drive time: {format_duration(best.duration_s)} "
                f"({compare(lambda r: format_duration(r.duration_s))})"
            )
        else:
            fastest = min(ranked, key=lambda r: r.duration_s)
            if fastest is best:
                reasons.append(f"Also the fastest option ({format_duration(best.duration_s)})")
            else:
                extra = format_duration(best.duration_s - fastest.duration_s)
                reasons.append(
                    f"Trade-off: {extra} longer than the fastest route "
                    f"({fastest.name}, {format_duration(fastest.duration_s)})"
                )
    else:
        reasons.append("Only one distinct route was found for this trip.")

    warning: str | None = None
    if best.summary.no_travel_miles > 0:
        warning = (
            "Every route crosses No-Travel conditions for this load and departure time. "
            "Consider delaying departure or reducing the load."
        )
    elif best.summary.severe_miles > 0:
        warning = (
            f"The recommended route still includes {best.summary.severe_miles:.0f} mi "
            "of Severe-risk conditions."
        )
    return reasons, warning
