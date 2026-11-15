import pytest

from routing.services import risk


@pytest.mark.parametrize(
    "mph,expected",
    [(0, "Low"), (24.9, "Low"), (25, "Moderate"), (34.9, "Moderate"), (35, "High"), (44.9, "High"),
     (45, "Severe"), (54.9, "Severe"), (55, "No Travel"), (80, "No Travel")],
)
def test_wind_bands(mph, expected):
    assert risk.wind_level(mph) == expected


@pytest.mark.parametrize(
    "in_hr,expected",
    [(0.0, "Low"), (0.099, "Low"), (0.10, "Moderate"), (0.249, "Moderate"), (0.25, "High"),
     (0.499, "High"), (0.50, "Severe"), (1.00, "Severe"), (1.001, "No Travel")],
)
def test_rain_bands(in_hr, expected):
    assert risk.rain_level(in_hr) == expected


@pytest.mark.parametrize(
    "in_hr,expected",
    [(0.49, "Low"), (0.5, "Moderate"), (0.99, "Moderate"), (1.0, "High"), (1.99, "High"),
     (2.0, "Severe"), (3.0, "Severe"), (3.01, "No Travel")],
)
def test_snow_bands(in_hr, expected):
    assert risk.snow_level(in_hr) == expected


@pytest.mark.parametrize(
    "mph,load,expected",
    [
        (50, 30_000, "Severe"),  # at the limit: no escalation
        (50, 30_001, "No Travel"),  # 45-54 mph and > 30,000 lb
        (54.9, 80_000, "No Travel"),
        (40, 40_000, "High"),  # at the limit: no escalation
        (40, 40_001, "Severe"),  # 35-44 mph and > 40,000 lb
        (44.9, 45_000, "Severe"),
        (60, 0, "No Travel"),  # >= 55 mph regardless of load
        (30, 80_000, "Moderate"),  # load rules only start at 35 mph
    ],
)
def test_load_rules(mph, load, expected):
    level, _ = risk.wind_level_for_load(mph, load)
    assert level == expected


def test_overall_is_worst_component():
    assessment = risk.assess_values(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0, load_lb=20_000)
    assert assessment.wind == "Low"
    assert assessment.rain == "High"
    assert assessment.overall == "High"
    assert assessment.score == 2
    assert any("Rain" in factor for factor in assessment.factors)


def test_factors_explain_load_escalation():
    assessment = risk.assess_values(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=45_000)
    assert assessment.overall == "Severe"
    assert "raised to Severe" in assessment.factors[0]
    assert "40,000 lb" in assessment.factors[0]


def test_calm_conditions_have_single_explanatory_factor():
    assessment = risk.assess_values(wind_mph=5, rain_in_hr=0, snow_in_hr=0, load_lb=80_000)
    assert assessment.overall == "Low"
    assert assessment.score == 0
    assert len(assessment.factors) == 1
