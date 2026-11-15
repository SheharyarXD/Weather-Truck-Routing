import pytest

from routing.services.summary import explain_recommendation, format_duration, rank_routes, summarize

from .helpers import planned_route


def test_summary_counts_miles_per_level_and_weighted_average():
    route = planned_route("A", [("Low", 50), ("High", 25), ("Severe", 25)])
    summary = summarize(route.checkpoints)
    assert summary.miles_by_level["Low"] == 50
    assert summary.high_miles == 25
    assert summary.severe_miles == 25
    assert summary.avg_risk == pytest.approx((0 * 50 + 2 * 25 + 3 * 25) / 100)
    assert summary.max_level == "Severe"
    assert summary.worst_checkpoint_index == 2
    assert summary.travelable


def _ranked(*routes):
    for route in routes:
        route.summary = summarize(route.checkpoints)
    return rank_routes(list(routes))


def test_rank_prefers_fewest_severe_then_high_then_avg_then_time():
    fast_but_severe = planned_route("A", [("Low", 90), ("Severe", 10)], mph=60)
    slow_and_calm = planned_route("B", [("Low", 100)], mph=40)
    high_only = planned_route("C", [("Low", 70), ("High", 30)], mph=50)
    ranked = _ranked(fast_but_severe, slow_and_calm, high_only)
    assert [r.id for r in ranked] == ["B", "C", "A"]
    assert ranked[0].recommended and ranked[0].rank == 1
    assert not ranked[1].recommended and ranked[2].rank == 3


def test_no_travel_miles_rank_last_even_with_fewer_severe_miles():
    no_travel = planned_route("A", [("Low", 95), ("No Travel", 5)])
    severe = planned_route("B", [("Low", 60), ("Severe", 40)])
    ranked = _ranked(no_travel, severe)
    assert [r.id for r in ranked] == ["B", "A"]


def test_time_breaks_ties_when_risk_is_identical():
    slower = planned_route("A", [("Moderate", 100)], mph=45)
    faster = planned_route("B", [("Moderate", 100)], mph=55)
    ranked = _ranked(slower, faster)
    assert ranked[0].id == "B"
    reasons, warning = explain_recommendation(ranked)
    assert reasons[-1].startswith("Shortest drive time")
    assert warning is None


def test_explanation_names_the_deciding_criterion_and_trade_off():
    severe_fast = planned_route("A", [("Low", 80), ("Severe", 20)], mph=60)
    calm_slow = planned_route("B", [("Low", 100)], mph=50)
    ranked = _ranked(severe_fast, calm_slow)
    reasons, warning = explain_recommendation(ranked)
    assert ranked[0].id == "B"
    assert reasons[0].startswith("Fewest Severe-risk miles: 0 mi")
    assert "Route A 20 mi" in reasons[0]
    assert reasons[-1].startswith("Trade-off")
    assert warning is None


def test_warning_when_every_route_has_no_travel_conditions():
    a = planned_route("A", [("No Travel", 10), ("Low", 90)])
    b = planned_route("B", [("No Travel", 30), ("Low", 70)])
    _, warning = explain_recommendation(_ranked(a, b))
    assert warning and "No-Travel" in warning


def test_format_duration():
    assert format_duration(0) == "0 min"
    assert format_duration(45 * 60) == "45 min"
    assert format_duration(9 * 3600 + 5 * 60) == "9h 05m"
