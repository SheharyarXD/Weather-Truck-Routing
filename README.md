# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest route based on **weather, load weight and
travel time**. It generates three route options, samples the forecast every 10 / 25 / 50 miles **at the truck's
estimated arrival time** at each checkpoint, classifies the risk with the assessment's wind / rain / snow and load
rules, recommends a route, and shows everything on a map together with a smooth 0–48 h corridor weather heatmap.

- **Live app:** https://sheharyarxd.github.io/Weather-Truck-Routing/
  (UI on GitHub Pages, Django API on Render's free tier: the first request after a quiet period can take up to a
  minute while the API wakes up, and the page shows a notice meanwhile)
- **Loom walkthrough:** https://www.loom.com/share/ed849d5909c44ecb96463ff10c4e2b04
- **Repository:** https://github.com/SheharyarXD/Weather-Truck-Routing

No API keys are required: routing uses [OSRM](https://project-osrm.org/), geocoding uses
[Photon](https://photon.komoot.io/) (with Nominatim as a fallback) and weather uses [Open-Meteo](https://open-meteo.com/).

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [How the logic works](#how-the-logic-works)
4. [API](#api)
5. [Running locally](#running-locally)
6. [Deployment](#deployment)
7. [Tests](#tests)
8. [Design decisions and assumptions](#design-decisions-and-assumptions)
9. [Limitations and next steps](#limitations-and-next-steps)
10. [Project structure](#project-structure)

---

## Features

| Requirement | Implementation |
| --- | --- |
| Inputs: origin, destination, departure date/time, load weight | Form with geocoding autocomplete (free text or `lat, lon` also accepted), `datetime-local` departure, load weight with presets, 10 / 25 / 50 mi checkpoint spacing |
| 3 route options from a routing API | OSRM `alternatives=3`, topped up with synthesized detours when OSRM returns fewer than three distinct routes |
| Weather every 10 / 25 / 50 miles at the truck's ETA | Checkpoints every N miles + destination; ETA from OSRM's per-edge durations; one batched Open-Meteo request per plan |
| Risk from the provided risk/load rules | `risk.py` implements the threshold table and the three load rules; overall risk = worst of wind / rain / snow |
| Recommendation balancing risk and time | Ranking: fewest No-Travel miles → fewest Severe miles → fewest High miles → lowest distance-weighted average risk → shortest drive time, with a generated explanation of the deciding criterion |
| Map with routes, checkpoints, risk levels, ETAs, summaries | Leaflet map: selected route coloured per checkpoint by risk, other routes muted, checkpoint markers with ETA/weather/risk popups, route summary labels placed where routes diverge, origin/destination pins |
| Corridor weather heatmap with a 0–48 h slider | Custom canvas heatmap (inverse-distance weighting, precomputed weights, bilinear upscaling) over a corridor grid; slider in 15-minute steps with playback, metric switch (Risk / Wind / Rain / Snow / Temp), truck position markers at the selected time |

## Architecture

```
frontend/  React 18 · TypeScript · Vite · Leaflet            backend/  Django 5 · Django REST framework (stateless, no DB)
┌────────────────────────────────────┐                        ┌────────────────────────────────────────────────┐
│ PlanForm + PlaceInput (autocomplete)│  GET  /api/geocode/   │ geocoding.py   Photon → Nominatim fallback      │
│ MapView                            │ ─────────────────────▶ │                                                │
│  ├ RouteLayers (risk-coloured)     │  POST /api/plan/      │ planner.plan_trip                              │
│  ├ CheckpointMarkers (popups)      │ ─────────────────────▶ │  ├ routing.py     OSRM alternatives + detours   │
│  ├ RouteLabels (summaries)         │ ◀──────────────────── │  ├ checkpoints.py every N mi, ETA per checkpoint│
│  ├ HeatCanvasLayer (IDW heatmap)   │  routes, checkpoints, │  ├ weather.py     Open-Meteo, batched + cached   │
│  └ TruckMarkers (position @ time)  │  recommendation, grid │  ├ risk.py        threshold + load rules         │
│ RecommendationPanel / RouteCards   │                        │  ├ summary.py     miles per level, ranking, text │
│ RouteDetails (checkpoint table)    │  POST /api/heatmap/   │  └ corridor.py    heatmap sampling grid          │
│ ForecastControls (0–48 h slider)   │ ─────────────────────▶ │ planner.heatmap   hourly risk/wind/rain/snow/temp│
└────────────────────────────────────┘                        └────────────────────────────────────────────────┘
```

In production a single Docker image serves both: the Vite build is collected into Django's static files and served by
WhiteNoise, gunicorn serves the API, and any non-API path returns the SPA.

## How the logic works

### 1. Route options (`backend/routing/services/routing.py`)

1. Ask OSRM for the trip with `alternatives=3`, `overview=full`, `steps=true` and per-edge `annotations=duration,distance`.
   The demo server usually returns one or two alternatives for long trips.
2. Provider routes that overlap another kept route by more than 90 % are dropped as duplicates.
3. If fewer than three distinct routes remain, **detours are synthesized**: via-points are placed perpendicular to the
   fastest route (offset = 12 % of the trip length, clamped to 12–160 km) on both sides of its midpoint and at one and
   two thirds of its length; a second round with the remaining thirds and a doubled offset runs only if needed. Each
   round routes its via-points `origin → via → destination` in parallel. A candidate is kept
   only if it is at most 1.5× the fastest drive time and shares less than 70 % of its length (within 2.5 km) with any
   route already kept. The similarity check takes the maximum of both directions so a route that merely adds a spur to
   another one is rejected.
4. Routes are named A / B / C in order of drive time and labelled with the roads that carry most of their distance
   (for example "via I-80 · I-15"), taken from OSRM step references.

OSRM's per-edge durations give a cumulative time profile along the full geometry, so ETAs reflect slow city streets
and fast interstates rather than an average speed.

### 2. Checkpoints and ETAs (`checkpoints.py`)

- Marks are placed at 0, N, 2N, … miles plus the destination. A regular mark that falls within 10 % of an interval of
  the destination is merged into it so the trip does not end with a near-duplicate checkpoint.
- ETA = departure time + cumulative route time at the mark (interpolated inside the edge).
- Each checkpoint **owns the stretch of road to the next checkpoint** (`segment_miles`); its weather and risk apply to
  that stretch. The destination owns zero miles but still counts towards the route's maximum risk level.
- Each checkpoint carries the simplified polyline of its stretch so the UI can colour the route by risk.

### 3. Weather at the ETA (`weather.py`)

- One batched Open-Meteo request covers every checkpoint of all routes for the window from departure to the last
  arrival (hourly `wind_speed_10m`, `wind_gusts_10m`, `rain`, `showers`, `snowfall`, `temperature_2m`, `weather_code`;
  units mph / inch / °F; UTC). Batches of 60 locations are fetched concurrently and cached for 15 minutes.
- At a checkpoint's ETA, wind, gusts and temperature are interpolated linearly between the two surrounding forecast
  hours; precipitation rates (in/hr) and the weather code come from the forecast hour containing the ETA, because they
  describe that whole hour. Rain = `rain + showers`; snow = `snowfall` in inches of snow per hour.
- Departures are accepted up to 10 days ahead (configurable), well inside Open-Meteo's 16-day horizon.

### 4. Risk rules (`risk.py`)

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules (applied to the wind component):

- ≥ 55 mph → **No Travel** for any load
- 45–54 mph and load > 30,000 lb → **No Travel**
- 35–44 mph and load > 40,000 lb → **Severe**

A checkpoint's overall level is the worst of the three components. Every band includes its lower bound; the rain and
snow "No Travel" bands are strictly greater than the Severe upper bound (`> 1.00`, `> 3.0`) while wind is No Travel
from exactly 55 mph (`≥ 55`), exactly as written in the brief. Each assessment carries human-readable factors such as
"Wind 38 mph: High raised to Severe (load over 40,000 lb in 35-44 mph wind)". The thresholds are covered by
table-driven unit tests including every boundary value.

### 5. Ranking and recommendation (`summary.py`)

Per route: miles per risk level (sum of the owned stretches), the distance-weighted average risk score
(Low = 0 … No Travel = 4) and the maximum level. Routes are sorted by

1. fewest **No-Travel** miles (treated as worse than Severe),
2. fewest **Severe** miles,
3. fewest **High** miles,
4. lowest **average risk**,
5. shortest **travel time**.

The explanation walks the criteria in order and names the first one that separates the routes
("Fewest High-risk miles: 12 mi (Route A 48 mi, Route C 30 mi)"), then states the time trade-off against the fastest
route. A warning is shown when even the recommended route includes Severe or No-Travel miles.

### 6. Corridor heatmap (`corridor.py`, `planner.heatmap`, `HeatCanvasLayer.ts`)

- The plan response includes a staggered sampling grid of at most 180 points within 40 miles of any route. The spacing
  adapts to the trip length, so a 100-mile and a 2,000-mile trip cost the same.
- `POST /api/heatmap/` returns, for every grid point, 49 hourly values (departure hour + 48 h) of risk score (with the
  load rules applied), wind, gusts, rain, snow and temperature.
- The frontend renders a custom Leaflet canvas layer. For the current viewport it precomputes, per 7-pixel cell, the
  eight nearest grid points and their inverse-distance weights (done once per pan/zoom). Moving the slider or
  switching metrics only re-blends those weights, which keeps scrubbing and playback smooth. Values are interpolated
  between forecast hours, the low-resolution field is upscaled with bilinear filtering, the corridor edge fades with a
  smoothstep falloff and the layer follows Leaflet's zoom animation.
- Truck markers show where each route's truck would be at the selected time; arrival times are marked under the slider.

## API

All endpoints return JSON. Errors have the shape `{"error": {"code": "...", "message": "...", "details": ...}}`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health/` | Liveness check |
| `GET` | `/api/geocode/?q=denv&limit=5` | Autocomplete suggestions `{results: [{label, lat, lng}]}` |
| `POST` | `/api/plan/` | Route options, checkpoints with weather + risk, recommendation, heatmap grid |
| `POST` | `/api/heatmap/` | Hourly weather and risk for the corridor grid |

`POST /api/plan/` request:

```json
{
  "origin": "Denver, CO",
  "destination": { "lat": 40.7608, "lng": -111.891, "label": "Salt Lake City" },
  "departure_time": "2026-11-16T15:00:00Z",
  "load_weight_lb": 35000,
  "sample_interval_miles": 25
}
```

Response (abridged):

```json
{
  "origin": { "label": "Denver, Colorado, United States", "lat": 39.7392, "lng": -104.9849 },
  "destination": { "...": "..." },
  "departure_time": "2026-11-16T15:00:00Z",
  "routes": [
    {
      "id": "A", "name": "Route A", "source": "osrm", "major_roads": ["I-80", "I-25"],
      "distance_miles": 518.7, "duration_seconds": 32460, "arrival_time": "2026-11-17T00:01:00Z",
      "geometry": [[39.7392, -104.9849], "..."],
      "checkpoints": [
        {
          "index": 1, "mile": 25.0, "segment_miles": 25.0, "lat": 40.05, "lng": -105.0,
          "eta": "2026-11-16T15:32:00Z", "hours_from_departure": 0.53, "is_destination": false,
          "path": [[40.05, -105.0], "..."],
          "weather": { "temp_f": 41.2, "wind_mph": 6.9, "gust_mph": 11.0, "rain_in_hr": 0.0, "snow_in_hr": 0.0,
                       "weather_code": 3, "description": "Overcast", "forecast_time": "2026-11-16T15:00:00Z" },
          "risk": { "wind": "Low", "rain": "Low", "snow": "Low", "overall": "Low", "score": 0,
                    "factors": ["Wind, rain and snow all within Low thresholds"] }
        }
      ],
      "summary": { "miles_by_level": { "Low": 518.7, "Moderate": 0, "High": 0, "Severe": 0, "No Travel": 0 },
                   "no_travel_miles": 0, "severe_miles": 0, "high_miles": 0, "avg_risk": 0.0,
                   "max_level": "Low", "worst_checkpoint_index": 0, "travelable": true },
      "rank": 1, "recommended": true
    }
  ],
  "recommendation": {
    "route_id": "A",
    "reasons": ["No Severe-risk miles on any route", "No High-risk miles on any route",
                "Same average risk on every route (0.00)", "Shortest drive time: 9h 01m (Route B 9h 46m, Route C 11h 13m)"],
    "warning": null,
    "criteria": ["Fewest No-Travel miles", "Fewest Severe miles", "Fewest High miles",
                 "Lowest average risk (distance-weighted)", "Shortest travel time"]
  },
  "heatmap": { "start": "2026-11-16T15:00:00Z", "hours": 48, "points": [[39.4, -105.2], "..."] },
  "timing_seconds": { "geocoding": 0.4, "routing": 3.1, "checkpoints": 0.3, "weather": 2.1, "ranking_and_grid": 0.2, "total": 6.1 }
}
```

`POST /api/heatmap/` takes `{points, start, hours, load_weight_lb}` straight from the plan response and returns
`{start, hours, times[49], points: [{lat, lng, risk[49], wind[49], gust[49], rain[49], snow[49], temp[49]}]}`.

Validation: departure must be between one hour ago and 10 days ahead, `sample_interval_miles` ∈ {10, 25, 50},
load weight 0–200,000 lb, trips up to 2,500 miles. Requests are throttled to 120/min per client.

## Running locally

Prerequisites: Python 3.12+, Node 20+.

```bash
# 1. Backend (http://127.0.0.1:8000)
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows   |   source .venv/bin/activate  (macOS/Linux)
pip install -r requirements.txt
python manage.py runserver

# 2. Frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Optional: copy `.env.example` to `.env` in the repository root to turn on `DJANGO_DEBUG`, point at a different OSRM
server, or tune limits. There is no database and nothing to migrate.

### Docker

```bash
docker compose up --build      # http://localhost:8000 serves the UI and the API
```

## Deployment

The live deployment is split in two, because GitHub Pages can only serve static files:

```
https://sheharyarxd.github.io/Weather-Truck-Routing/   React build (GitHub Pages, .github/workflows/pages.yml)
        │  fetch, CORS
        ▼
https://sheharyarxd-weather-routing.onrender.com/api/  Django API (Render free tier, render.yaml + Dockerfile)
```

**1. API on Render (free tier):** New → Blueprint → select this repository. Render builds the Dockerfile, injects
`RENDER_EXTERNAL_HOSTNAME` (added to `ALLOWED_HOSTS` automatically), generates `DJANGO_SECRET_KEY` and sets
`CORS_ALLOWED_ORIGINS` to the GitHub Pages origin. The health check is `/api/health/`. The Render URL also serves the
complete app on its own.

**2. UI on GitHub Pages:** in the repository settings, set Pages → Build and deployment → Source to **GitHub
Actions**. Every push to `main` then builds the frontend with `VITE_BASE=/<repository>/` and
`VITE_API_BASE=https://sheharyarxd-weather-routing.onrender.com/api` and publishes it. If Render assigns a different
URL, set the repository variable `API_BASE_URL` (Settings → Secrets and variables → Actions → Variables) to
`https://<your-service>.onrender.com/api` and re-run the workflow.

Free Render services sleep after 15 minutes without traffic. The page pings `/api/health/` as soon as it loads, so the
API wakes while the driver fills in the form, and a notice explains the wait.

**Any other Docker host** (Railway, Fly.io, a VPS): build the image and set `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS=<your host>` and optionally `WEB_CONCURRENCY`. Set `VITE_API_BASE` only if the UI is hosted on a
different origin than the API (then also set `CORS_ALLOWED_ORIGINS`).

## Tests

```bash
cd backend && pytest             # 88 tests: risk thresholds & load rules, geo maths, checkpoints/ETAs,
                                 # ranking & explanations, corridor grid, Open-Meteo client (mocked HTTP),
                                 # OSRM parsing + detour synthesis (fake router), API contract, validation, CORS
cd frontend && npm run typecheck && npm test && npm run build
```

External services are faked in the tests so they run offline; `.github/workflows/ci.yml` runs both suites on push.

## Design decisions and assumptions

- **Stateless API, no database.** Every plan is computed on request from third-party data; responses and upstream
  calls are cached in process (routes 30 min, weather 15 min, geocodes 24 h). This keeps deployment to a single
  container and makes repeated requests near-instant.
- **No-Travel ranks before Severe.** The brief ranks by Severe miles first; No-Travel conditions are strictly worse,
  so they are compared first. A route crossing No-Travel conditions is flagged "not travelable" but still shown.
- **Average risk is distance-weighted** over the stretches owned by each checkpoint, so a 10-mile and a 50-mile
  sampling interval give comparable averages.
- **Checkpoint ownership.** A checkpoint's weather applies to the road until the next checkpoint. Alternatives (e.g.
  midpoint sampling) were rejected for clarity: the driver sees "Mile 125, 10:32 AM, High – applies to the next 25 mi".
- **Boundary handling** follows the table literally (see §4). Exactly 1.00 in/hr of rain is Severe; exactly 55 mph is
  No Travel.
- **Truck speeds.** OSRM's public servers only offer a car profile. Drive times are used as returned by default;
  `TRUCK_DURATION_FACTOR` (e.g. `1.1`) scales all durations if slower truck speeds should be modelled. The backend is
  OSRM-compatible, so a self-hosted OSRM with a truck profile can be swapped in via `OSRM_BASE_URL`.
- **Time zones.** The API works in UTC (ISO-8601 with `Z`); the UI formats every time in the browser's local zone.
- **Synthesized detours are labelled** (`source: "osrm-detour"`) so it is transparent which option came straight from
  the routing API.
- **Heatmap time base.** Slider hour 0 is the departure hour (floored to the hour); truck markers account for the
  minutes between that hour and the actual departure.

## Limitations and next steps

- Public demo servers (OSRM, Photon, Open-Meteo) have fair-use limits and variable latency. Planning time is dominated
  by the OSRM round trips (typically 3–10 s for a cross-country trip when detours have to be synthesized); the batched
  weather fetch takes about a second even for 300 checkpoints, and repeated requests are served from cache.
- OSRM has no truck restrictions (bridge heights, weight limits, hazmat). A self-hosted OSRM/Valhalla truck profile or
  a commercial truck-routing API would plug into `OSRMRouter` / `fetch_route_options`.
- Risk is computed from sustained 10 m wind speed as the brief specifies; gusts are shown but not scored.
- Possible extensions: departure-time optimisation ("leave 3 h later to avoid the front"), per-checkpoint rest/HOS
  planning, saving plans, and WebSocket progress updates during planning.

## Project structure

```
backend/
  config/settings.py            Django settings (env-driven, no DB, WhiteNoise, DRF)
  routing/
    views.py, serializers.py    API layer and validation
    exceptions.py               Domain errors → JSON error responses
    services/
      domain.py                 Dataclasses shared by all services
      geo.py                    Haversine, interpolation along polylines, Douglas-Peucker, spatial hash
      geocoding.py              Photon / Nominatim
      routing.py                OSRM client, parsing, similarity, detour synthesis
      checkpoints.py            Sampling every N miles + ETAs
      weather.py                Open-Meteo client, hourly series, ETA sampling
      risk.py                   Threshold table + load rules
      summary.py                Miles per level, ranking, explanation
      corridor.py               Heatmap sampling grid
      planner.py                Orchestration for /api/plan and /api/heatmap
    tests/                      pytest suite (fakes for all external services)
frontend/
  src/App.tsx                   State, data flow, playback
  src/api/client.ts             Typed API client
  src/lib/                      risk colours, formatting, geo helpers, heatmap colour scales (+ vitest)
  src/components/               Form, autocomplete, recommendation, route cards, checkpoint table, forecast controls
  src/components/map/           Map, route layers, checkpoint markers, labels, truck markers, canvas heatmap
Dockerfile, docker-compose.yml, render.yaml, .env.example
.github/workflows/ci.yml        Tests, typecheck and build on every push
.github/workflows/pages.yml     Deploys the frontend to GitHub Pages
WALKTHROUGH.md                  Script for the Loom video
```

## Credits

Routing data © [OSRM](https://project-osrm.org/) / OpenStreetMap contributors · Geocoding © [Photon](https://photon.komoot.io/)
and [Nominatim](https://nominatim.org/) · Weather © [Open-Meteo](https://open-meteo.com/) (CC BY 4.0) ·
Basemap tiles © Esri (World Light Gray Canvas; switchable to OpenStreetMap or any XYZ provider via `VITE_BASEMAP` / `VITE_TILE_URL`).
