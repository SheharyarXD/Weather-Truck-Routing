"""Weather risk rules from the assessment brief.

Thresholds (per checkpoint)::

    Condition   Low          Moderate     High         Severe       No Travel
    Wind        <25 mph      25-34        35-44        45-54        >=55 mph
    Rain        <0.10 in/hr  0.10-0.25    0.25-0.50    0.50-1.00    >1.00
    Snow        <0.5 in/hr   0.5-1.0      1.0-2.0      2.0-3.0      >3.0

Boundary convention: every band includes its lower bound. The rain/snow
"No Travel" bands are strictly greater than the Severe upper bound (``>1.00``,
``>3.0``), so exactly 1.00 in/hr of rain is Severe, whereas wind is No Travel
from exactly 55 mph (``>=55``).

Load rules (applied to the wind component)::

    >=55 mph                        -> No Travel for any load
    45-54 mph and load > 30,000 lb  -> No Travel
    35-44 mph and load > 40,000 lb  -> Severe

A checkpoint's overall risk is the worst of its three components.
"""
from __future__ import annotations

from typing import Iterable

from .domain import RiskAssessment, WeatherSample

LEVELS: tuple[str, ...] = ("Low", "Moderate", "High", "Severe", "No Travel")
SCORES: dict[str, int] = {level: i for i, level in enumerate(LEVELS)}

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = LEVELS

WIND_BANDS_MPH = (25.0, 35.0, 45.0, 55.0)
RAIN_BANDS_IN_HR = (0.10, 0.25, 0.50, 1.00)
SNOW_BANDS_IN_HR = (0.5, 1.0, 2.0, 3.0)

LOAD_NO_TRAVEL_LB = 30_000  # combined with 45-54 mph wind
LOAD_SEVERE_LB = 40_000  # combined with 35-44 mph wind


def wind_level(mph: float) -> str:
    if mph >= WIND_BANDS_MPH[3]:
        return NO_TRAVEL
    if mph >= WIND_BANDS_MPH[2]:
        return SEVERE
    if mph >= WIND_BANDS_MPH[1]:
        return HIGH
    if mph >= WIND_BANDS_MPH[0]:
        return MODERATE
    return LOW


def _precip_level(value: float, bands: tuple[float, float, float, float]) -> str:
    if value > bands[3]:
        return NO_TRAVEL
    if value >= bands[2]:
        return SEVERE
    if value >= bands[1]:
        return HIGH
    if value >= bands[0]:
        return MODERATE
    return LOW


def rain_level(in_hr: float) -> str:
    return _precip_level(in_hr, RAIN_BANDS_IN_HR)


def snow_level(in_hr: float) -> str:
    return _precip_level(in_hr, SNOW_BANDS_IN_HR)


def wind_level_for_load(mph: float, load_lb: float) -> tuple[str, str | None]:
    """Wind level after the load rules. Returns ``(level, note)``; ``note`` explains an escalation."""
    base = wind_level(mph)
    if base == NO_TRAVEL:
        return NO_TRAVEL, None
    if base == SEVERE and load_lb > LOAD_NO_TRAVEL_LB:
        return NO_TRAVEL, f"load over {LOAD_NO_TRAVEL_LB:,} lb in 45-54 mph wind"
    if base == HIGH and load_lb > LOAD_SEVERE_LB:
        return SEVERE, f"load over {LOAD_SEVERE_LB:,} lb in 35-44 mph wind"
    return base, None


def max_level(levels: Iterable[str]) -> str:
    return max(levels, key=lambda level: SCORES[level])


def assess_values(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> RiskAssessment:
    wind, note = wind_level_for_load(wind_mph, load_lb)
    rain = rain_level(rain_in_hr)
    snow = snow_level(snow_in_hr)
    overall = max_level((wind, rain, snow))

    factors: list[str] = []
    if wind != LOW:
        if note:
            factors.append(f"Wind {wind_mph:.0f} mph: {wind_level(wind_mph)} raised to {wind} ({note})")
        else:
            factors.append(f"Wind {wind_mph:.0f} mph: {wind}")
    if rain != LOW:
        factors.append(f"Rain {rain_in_hr:.2f} in/hr: {rain}")
    if snow != LOW:
        factors.append(f"Snow {snow_in_hr:.1f} in/hr: {snow}")
    if not factors:
        factors.append("Wind, rain and snow all within Low thresholds")

    return RiskAssessment(
        wind=wind,
        rain=rain,
        snow=snow,
        overall=overall,
        score=SCORES[overall],
        factors=tuple(factors),
    )


def assess(sample: WeatherSample, load_lb: float) -> RiskAssessment:
    return assess_values(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, load_lb)
