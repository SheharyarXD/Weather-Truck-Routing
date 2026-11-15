from __future__ import annotations

from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .services.domain import Place

SAMPLE_INTERVALS_MILES = (10, 25, 50)


class PlaceField(serializers.Field):
    """Either a free-text place name or ``{"lat": .., "lng": .., "label"?: ..}``."""

    default_error_messages = {
        "invalid": "Provide a place name (at least 2 characters) or an object with lat/lng.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            text = data.strip()
            if len(text) < 2:
                self.fail("invalid")
            return text
        if isinstance(data, dict):
            try:
                lat = float(data.get("lat"))
                lon = float(data.get("lng", data.get("lon")))
            except (TypeError, ValueError):
                self.fail("invalid")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self.fail("invalid")
            label = str(data.get("label") or f"{lat:.5f}, {lon:.5f}")
            return Place(label=label, lat=lat, lon=lon)
        self.fail("invalid")

    def to_representation(self, value):
        return value.to_dict() if isinstance(value, Place) else value


def _validate_departure(value, *, allow_past_hours: float):
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    value = value.astimezone(dt_timezone.utc)
    now = timezone.now()
    if value < now - timedelta(hours=allow_past_hours):
        raise serializers.ValidationError("Departure time must not be in the past.")
    max_days = settings.TRUCK_ROUTING["MAX_DEPARTURE_DAYS_AHEAD"]
    if value > now + timedelta(days=max_days):
        raise serializers.ValidationError(
            f"Departure time must be within the next {max_days} days (weather forecast horizon)."
        )
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure_time = serializers.DateTimeField()
    load_weight_lb = serializers.FloatField(min_value=0, max_value=200_000)
    sample_interval_miles = serializers.ChoiceField(choices=SAMPLE_INTERVALS_MILES, default=25)

    def validate_departure_time(self, value):
        return _validate_departure(value, allow_past_hours=1)


class HeatmapRequestSerializer(serializers.Serializer):
    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=1,
        max_length=400,
    )
    start = serializers.DateTimeField()
    hours = serializers.IntegerField(min_value=1, max_value=48, default=48)
    load_weight_lb = serializers.FloatField(min_value=0, max_value=200_000)

    def validate_start(self, value):
        return _validate_departure(value, allow_past_hours=48)

    def validate_points(self, value):
        for lat, lon in value:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Point out of range.")
        return [(lat, lon) for lat, lon in value]


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200)
    limit = serializers.IntegerField(min_value=1, max_value=10, default=5)
