# Walkthrough

## Narration-free video (generated)

`walkthrough.mp4` is produced automatically by [tools/walkthrough/record.js](tools/walkthrough/record.js): it starts
the Django server with the built frontend, drives the real UI in a headless Chromium with Playwright, overlays large
captions and a visible cursor, records at 1920×1080 and converts the recording to MP4 (≈5 minutes, no audio). Upload
it to Loom as-is, or use it as the screen track and add narration from the script below.

```bash
cd frontend && npm run build && cd ../backend && python manage.py collectstatic --noinput
cd ../tools/walkthrough && npm install && npx playwright install chromium
npm run record          # env: ORIGIN / DESTINATION / LOAD / OUTPUT / APP_URL
```

Pick an origin/destination pair that has some weather on the day you record; the default (Portland → Boise,
45,000 lb) is only a starting point.

## Narrated Loom script (target 6–8 minutes)

Record at 1080p with the browser on the left two-thirds of the screen and your editor ready in another tab.
Have the app already loaded (empty state) before pressing record. Times are cumulative.

## 0:00 – 0:40 · Problem and stack
- "This is a weather-aware truck routing app: React + TypeScript + Leaflet on the front, Django + DRF on the back."
- "The driver enters origin, destination, departure time and load weight. The app generates three routes, samples the
  forecast every 10 / 25 / 50 miles **at the truck's ETA**, applies the risk and load rules from the brief, and
  recommends a route. Everything is shown on a map with a 48-hour corridor heatmap."
- Mention it uses free public APIs with no keys: OSRM for routing, Photon/Nominatim for geocoding, Open-Meteo for weather.

## 0:40 – 2:00 · Plan a trip (live)
- Type "Denver" → show autocomplete → pick Denver, Colorado. Destination: Salt Lake City (or any pair with weather today).
- Set departure a few hours out, load weight 35,000 lb, interval 25 mi. Click **Plan routes**.
- While it loads (≈5–10 s): "One request geocodes both ends in parallel, asks OSRM for alternatives, synthesises
  detours if OSRM only returns one or two, samples checkpoints, then makes one batched Open-Meteo call for every
  checkpoint over the trip's time window."

## 2:00 – 3:30 · Map: routes, checkpoints, ETAs, summaries
- Point at the three routes; the selected one is coloured per checkpoint by risk, the others are grey.
- Hover a checkpoint: mile, ETA, risk. Click one: popup with weather (wind, gusts, rain, snow, temperature), the
  risk badge and the **reasons** (e.g. "Wind 38 mph: High raised to Severe (load over 40,000 lb)").
- Point at the route labels placed where routes diverge ("B · 9h 44m · 525 mi · #2 · High").
- Click a grey route to switch selection; show that cards, table and map stay in sync.

## 3:30 – 4:30 · Recommendation and ranking
- Read the recommendation card: deciding criterion is spelled out ("Fewest High-risk miles: 12 mi (Route A 48 mi …)")
  plus the trade-off line against the fastest route.
- Open "How routes are ranked": No-Travel miles → Severe miles → High miles → distance-weighted average risk → time.
- Scroll the route cards: stacked risk bar = miles per level; show the checkpoint table, click a row to fly to it.
- Change the load to 45,000 lb and re-plan: show how wind checkpoints escalate (High → Severe, Severe → No Travel)
  and how the recommendation/warning changes. (If the weather is calm everywhere, say so and show the unit tests
  for the thresholds instead: `backend/routing/tests/test_risk.py`.)

## 4:30 – 5:45 · Heatmap and 0–48 h slider
- Scrub the slider: "The heatmap is a custom canvas layer. For the current view it precomputes the 8 nearest forecast
  cells and their inverse-distance weights once per pan/zoom; moving the slider only re-blends, so it stays at 60 fps."
- Press **play**; point out the truck markers moving along each route at the selected time and the arrival ticks under
  the slider.
- Switch metrics: Risk → Wind → Rain → Snow → Temp. Zoom in/out to show the layer following the map smoothly.

## 5:45 – 7:00 · Code tour (quick)
- `backend/routing/services/risk.py` – the thresholds and load rules, one screen, fully unit-tested.
- `checkpoints.py` – marks every N miles + destination, ETA from OSRM's per-edge durations.
- `routing.py` – `fetch_route_options`: OSRM alternatives + perpendicular via-point detours + similarity de-dup.
- `summary.py` – ranking key and the generated explanation.
- `frontend/src/components/map/HeatCanvasLayer.ts` – the IDW canvas heatmap.
- Show `pytest` output (87 tests) and `npm test`.

## 7:00 – 7:30 · Deployment and wrap-up
- Single Docker image (frontend built into Django static files, served by WhiteNoise + gunicorn); `render.yaml`
  blueprint; CI runs both test suites.
- Limitations in one breath: OSRM car profile (no public truck profile; `TRUCK_DURATION_FACTOR` is available), public
  demo servers, forecast horizon 10 days.
