from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import GeocodeQuerySerializer, HeatmapRequestSerializer, PlanRequestSerializer
from .services.geocoding import suggest
from .services.planner import PlanRequest, heatmap, plan_trip


class HealthView(APIView):
    throttle_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "time": timezone.now().isoformat()})


class GeocodeView(APIView):
    """``GET /api/geocode/?q=den`` -> place suggestions for autocomplete."""

    def get(self, request: Request) -> Response:
        params = GeocodeQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        places = suggest(params.validated_data["q"], params.validated_data["limit"])
        return Response({"results": [place.to_dict() for place in places]})


class PlanView(APIView):
    """``POST /api/plan/`` -> route options, checkpoints with weather/risk, recommendation."""

    def post(self, request: Request) -> Response:
        body = PlanRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = plan_trip(
            PlanRequest(
                origin=data["origin"],
                destination=data["destination"],
                departure=data["departure_time"],
                load_lb=data["load_weight_lb"],
                interval_miles=float(data["sample_interval_miles"]),
            )
        )
        return Response(result)


class HeatmapView(APIView):
    """``POST /api/heatmap/`` -> hourly weather + risk for corridor points (0-48 h)."""

    def post(self, request: Request) -> Response:
        body = HeatmapRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        return Response(heatmap(data["points"], data["start"], data["hours"], data["load_weight_lb"]))


_FALLBACK_INDEX = """<!doctype html><html><head><meta charset="utf-8">
<title>Weather-Aware Truck Routing API</title></head>
<body style="font-family:system-ui;margin:3rem;max-width:40rem">
<h1>Weather-Aware Truck Routing API</h1>
<p>The frontend build was not found. For development run <code>npm run dev</code> in
<code>frontend/</code>; for production build the Docker image.</p>
<p>API health: <a href="/api/health/">/api/health/</a></p></body></html>"""


def spa_index(request: HttpRequest) -> HttpResponse:
    """Serve the built single-page app (Vite output) for any non-API path."""
    for candidate in (settings.FRONTEND_DIST / "index.html", settings.STATIC_ROOT / "index.html"):
        if candidate.is_file():
            return HttpResponse(candidate.read_text(encoding="utf-8"), content_type="text/html")
    return HttpResponse(_FALLBACK_INDEX, content_type="text/html")
