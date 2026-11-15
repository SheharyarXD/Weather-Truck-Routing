"""
Django settings for the Weather-Aware Truck Routing API.

The API is stateless: there is no database and no session state. All data
comes from third-party services (OSRM for routing, Photon/Nominatim for
geocoding, Open-Meteo for weather) and is cached in-process.

Configuration is read from environment variables; a ``.env`` file in the
repository root is loaded if present (see ``.env.example``).
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_DIR = BASE_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines, '#' comments). Never overrides real env vars."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(REPO_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", REPO_DIR / "frontend" / "dist"))

# --- Core -------------------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["*"] if DEBUG else ["localhost", "127.0.0.1"])
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

# No database: the service is a pure computation/proxy layer.
DATABASES: dict = {}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truck-routing",
        "OPTIONS": {"MAX_ENTRIES": 2000},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# --- Static files / SPA -------------------------------------------------------
# The production Docker image builds the React app into frontend/dist with
# Vite's ``base`` set to ``/static/`` so WhiteNoise can serve the hashed assets.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.is_dir() else []
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_MAX_AGE = 0 if DEBUG else 60 * 60 * 24 * 30

# --- CORS (only needed when the Vite dev server talks to the API directly) ---

CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]
)

# --- Django REST framework ----------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": os.environ.get("API_THROTTLE_RATE", "120/min")},
    "EXCEPTION_HANDLER": "routing.exceptions.exception_handler",
}

# --- Application settings -----------------------------------------------------

TRUCK_ROUTING = {
    # Routing (OSRM HTTP API; any OSRM-compatible server works).
    "OSRM_BASE_URL": os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org"),
    "OSRM_PROFILE": os.environ.get("OSRM_PROFILE", "driving"),
    # Multiply car-profile durations to approximate truck speeds (1.0 = use API values as-is).
    "TRUCK_DURATION_FACTOR": float(os.environ.get("TRUCK_DURATION_FACTOR", "1.0")),
    "ROUTE_OPTIONS": 3,
    # Geocoding.
    "PHOTON_URL": os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/"),
    "NOMINATIM_URL": os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"),
    # Weather.
    "OPEN_METEO_URL": os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"),
    "WEATHER_BATCH_SIZE": int(os.environ.get("WEATHER_BATCH_SIZE", "60")),
    # HTTP.
    "USER_AGENT": os.environ.get("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0"),
    "HTTP_TIMEOUT_SECONDS": float(os.environ.get("HTTP_TIMEOUT_SECONDS", "45")),
    # Limits.
    "MAX_TRIP_MILES": float(os.environ.get("MAX_TRIP_MILES", "2500")),
    "MAX_DEPARTURE_DAYS_AHEAD": int(os.environ.get("MAX_DEPARTURE_DAYS_AHEAD", "10")),
    # Heatmap corridor.
    "HEATMAP_MAX_POINTS": int(os.environ.get("HEATMAP_MAX_POINTS", "180")),
    "HEATMAP_CORRIDOR_MILES": float(os.environ.get("HEATMAP_CORRIDOR_MILES", "40")),
    "HEATMAP_HOURS": 48,
    # Cache TTLs (seconds).
    "WEATHER_CACHE_SECONDS": 15 * 60,
    "ROUTE_CACHE_SECONDS": 30 * 60,
    "GEOCODE_CACHE_SECONDS": 24 * 60 * 60,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
