import { useCallback, useEffect, useRef, useState } from 'react';

import { describeError, fetchHeatmap, planTrip } from './api/client';
import { useApiStatus } from './api/useApiStatus';
import { ForecastControls } from './components/ForecastControls';
import { PlanForm } from './components/PlanForm';
import { RecommendationPanel } from './components/RecommendationPanel';
import { RouteCards } from './components/RouteCards';
import { RouteDetails } from './components/RouteDetails';
import { MapView, type Focus } from './components/map/MapView';
import type { HeatmapMetric, HeatmapResponse, PlanRequest, PlanResponse } from './types';

const PLAYBACK_STEP_HOURS = 0.25;
const PLAYBACK_INTERVAL_MS = 120;

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus | null>(null);

  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [metric, setMetric] = useState<HeatmapMetric>('risk');
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const apiStatus = useApiStatus();

  const submit = useCallback(async (request: PlanRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPlanning(true);
    setError(null);
    setHeatmap(null);
    setHeatmapError(null);
    setPlaying(false);
    setFocus(null);

    try {
      const result = await planTrip(request, controller.signal);
      if (controller.signal.aborted) return;
      setPlan(result);
      setSelectedId(result.recommendation.route_id);
      setHour(0);

      setHeatmapLoading(true);
      fetchHeatmap(
        {
          points: result.heatmap.points,
          start: result.heatmap.start,
          hours: result.heatmap.hours,
          load_weight_lb: result.load_weight_lb,
        },
        controller.signal,
      )
        .then((data) => {
          if (!controller.signal.aborted) setHeatmap(data);
        })
        .catch((err) => {
          if (!controller.signal.aborted) setHeatmapError(describeError(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setHeatmapLoading(false);
        });
    } catch (err) {
      if (!controller.signal.aborted) setError(describeError(err));
    } finally {
      if (!controller.signal.aborted) setPlanning(false);
    }
  }, []);

  // Forecast playback.
  useEffect(() => {
    if (!playing || !heatmap) return;
    const maxHour = heatmap.hours;
    const timer = window.setInterval(() => {
      setHour((current) => (current + PLAYBACK_STEP_HOURS > maxHour ? 0 : current + PLAYBACK_STEP_HOURS));
    }, PLAYBACK_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [playing, heatmap]);

  const selectRoute = useCallback((id: string) => {
    setSelectedId(id);
    setFocus(null);
  }, []);

  const selectedRoute = plan?.routes.find((route) => route.id === selectedId) ?? null;

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <img src={`${import.meta.env.BASE_URL}truck.svg`} alt="" width={36} height={36} />
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Compare route options by forecast risk, load weight and drive time.</p>
          </div>
        </header>

        {apiStatus === 'waking' && (
          <div className="alert alert-warning api-status" role="status">
            <div className="spinner small-spinner" />
            <div>
              <strong>Waking up the API server…</strong> It runs on a free hosting tier that sleeps when idle, so the
              first request can take up to a minute. You can fill in the form meanwhile.
            </div>
          </div>
        )}
        {apiStatus === 'offline' && (
          <div className="alert alert-error api-status" role="alert">
            The API server is not reachable right now. Please reload the page in a minute.
          </div>
        )}

        <PlanForm onSubmit={submit} busy={planning} />

        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {planning && (
          <div className="panel loading-panel" aria-live="polite">
            <div className="spinner" />
            <div>
              <strong>Planning your trip…</strong>
              <div className="muted small">Geocoding → routing 3 options → sampling the forecast at every checkpoint</div>
            </div>
          </div>
        )}

        {plan && !planning && (
          <>
            <RecommendationPanel plan={plan} onSelect={selectRoute} />
            <RouteCards routes={plan.routes} selectedId={selectedId} onSelect={selectRoute} />
            {selectedRoute && (
              <RouteDetails
                route={selectedRoute}
                intervalMiles={plan.sample_interval_miles}
                focusIndex={focus?.routeId === selectedRoute.id ? focus.index : null}
                onFocusCheckpoint={(index) => setFocus({ routeId: selectedRoute.id, index })}
              />
            )}
          </>
        )}

        {!plan && !planning && !error && (
          <section className="panel intro">
            <h2>How it works</h2>
            <ol>
              <li>Three route options are generated with the OSRM routing API.</li>
              <li>Every 10 / 25 / 50 miles the forecast is sampled at the truck's estimated arrival time.</li>
              <li>Wind, rain and snow are classified Low → No Travel, with wind escalated for heavy loads.</li>
              <li>Routes are ranked by Severe miles, High miles, average risk, then drive time.</li>
            </ol>
            <p className="muted small">
              Weather by Open-Meteo. Forecasts are available up to 10 days ahead; the heatmap covers the 48 hours after
              departure.
            </p>
          </section>
        )}

        <footer className="sidebar-footer muted small">
          Routing © OSRM · Geocoding © Photon / OpenStreetMap · Weather © Open-Meteo
        </footer>
      </aside>

      <main className="map-area">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={selectRoute}
          heatmap={heatmap}
          metric={metric}
          hour={hour}
          showHeatmap={showHeatmap}
          focus={focus}
        />
        {plan && (
          <ForecastControls
            plan={plan}
            heatmap={heatmap}
            loading={heatmapLoading}
            error={heatmapError}
            hour={hour}
            onHour={setHour}
            metric={metric}
            onMetric={setMetric}
            playing={playing}
            onTogglePlay={() => setPlaying((value) => !value)}
            visible={showHeatmap}
            onToggleVisible={() => setShowHeatmap((value) => !value)}
          />
        )}
      </main>
    </div>
  );
}
