"""Domain exceptions and the DRF exception handler that renders them as JSON."""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ServiceError(Exception):
    """Base class for errors that should become a JSON error response."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "service_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details


class GeocodingError(ServiceError):
    code = "geocoding_failed"


class RoutingError(ServiceError):
    code = "routing_failed"


class WeatherError(ServiceError):
    code = "weather_failed"


class PlanningError(ServiceError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid_plan"


def exception_handler(exc: Exception, context: dict) -> Response | None:
    """Render every error as ``{"error": {"code", "message", "details?"}}``."""
    if isinstance(exc, ServiceError):
        body: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
        if exc.details is not None:
            body["error"]["details"] = exc.details
        return Response(body, status=exc.status_code)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and set(data) == {"detail"}:
        message, details = str(data["detail"]), None
    else:
        message, details = "Request validation failed.", data
    code = "validation_error" if response.status_code == 400 else "request_error"
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    response.data = body
    return response
