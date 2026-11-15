"""Geocoding via Photon (komoot) with Nominatim as a fallback. Results are cached."""
from __future__ import annotations

import hashlib
import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache

from ..exceptions import GeocodingError
from .domain import Place
from .http import get_session, timeout

log = logging.getLogger(__name__)

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _cache_key(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _photon_label(props: dict) -> str:
    parts: list[str] = []
    name = props.get("name")
    street = props.get("street")
    housenumber = props.get("housenumber")
    if name:
        parts.append(name)
    if street and street != name:
        parts.append(f"{housenumber} {street}".strip() if housenumber else street)
    for key in ("city", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def _photon(query: str, limit: int) -> list[Place]:
    resp = get_session().get(
        settings.TRUCK_ROUTING["PHOTON_URL"],
        params={"q": query, "limit": limit, "lang": "en"},
        timeout=timeout(),
    )
    resp.raise_for_status()
    places: list[Place] = []
    for feature in resp.json().get("features", []):
        coords = feature.get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        label = _photon_label(feature.get("properties", {})) or query
        places.append(Place(label=label, lat=float(coords[1]), lon=float(coords[0])))
    return places


def _nominatim(query: str, limit: int) -> list[Place]:
    resp = get_session().get(
        settings.TRUCK_ROUTING["NOMINATIM_URL"],
        params={"q": query, "format": "jsonv2", "limit": limit},
        timeout=timeout(),
    )
    resp.raise_for_status()
    return [
        Place(label=item.get("display_name", query), lat=float(item["lat"]), lon=float(item["lon"]))
        for item in resp.json()
        if "lat" in item and "lon" in item
    ]


def suggest(query: str, limit: int = 5) -> list[Place]:
    """Autocomplete suggestions (Photon only: Nominatim's usage policy forbids autocomplete)."""
    query = query.strip()
    if len(query) < 2:
        return []
    key = _cache_key("geo:suggest", query.lower(), limit)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        places = _photon(query, limit)
    except (requests.RequestException, ValueError) as exc:
        log.warning("Photon suggest failed for %r: %s", query, exc)
        return []
    cache.set(key, places, 60 * 60)
    return places


def geocode(query: str) -> Place:
    """Resolve free text (or a ``"lat, lon"`` pair) to a single place."""
    query = query.strip()
    match = _COORD_RE.match(query)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise GeocodingError(f"Coordinates out of range: {query!r}", status_code=400)
        return Place(label=f"{lat:.5f}, {lon:.5f}", lat=lat, lon=lon)

    key = _cache_key("geo:one", query.lower())
    cached = cache.get(key)
    if cached is not None:
        return cached

    failures: list[str] = []
    for provider in (_photon, _nominatim):
        try:
            places = provider(query, 1)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{provider.__name__.strip('_')}: {exc}")
            continue
        if places:
            cache.set(key, places[0], settings.TRUCK_ROUTING["GEOCODE_CACHE_SECONDS"])
            return places[0]

    if len(failures) == 2:
        raise GeocodingError(
            "Geocoding services are unavailable right now. Please try again.", details=failures
        )
    raise GeocodingError(
        f"Could not find a location for {query!r}. Try adding a state or country.", status_code=400
    )
