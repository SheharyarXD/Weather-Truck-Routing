import { formatDayTime, formatHourOffset, formatTime } from '../lib/format';
import { METRICS, METRIC_ORDER } from '../lib/heatmap';
import { routeColor } from '../lib/risk';
import type { HeatmapMetric, HeatmapResponse, PlanResponse } from '../types';
import { Legend } from './Legend';

interface Props {
  plan: PlanResponse;
  heatmap: HeatmapResponse | null;
  loading: boolean;
  error: string | null;
  hour: number;
  onHour: (hour: number) => void;
  metric: HeatmapMetric;
  onMetric: (metric: HeatmapMetric) => void;
  playing: boolean;
  onTogglePlay: () => void;
  visible: boolean;
  onToggleVisible: () => void;
}

export function ForecastControls({
  plan,
  heatmap,
  loading,
  error,
  hour,
  onHour,
  metric,
  onMetric,
  playing,
  onTogglePlay,
  visible,
  onToggleVisible,
}: Props) {
  const hours = heatmap?.hours ?? plan.heatmap.hours;
  const startMs = new Date(plan.heatmap.start).getTime();
  const currentMs = startMs + hour * 3600 * 1000;
  const spec = METRICS[metric];
  const percent = (iso: string) => `${Math.min(100, Math.max(0, ((new Date(iso).getTime() - startMs) / 3600000 / hours) * 100))}%`;

  return (
    <div className={`forecast-panel${visible ? '' : ' collapsed'}`}>
      <div className="forecast-header">
        <div>
          <strong>Corridor weather heatmap</strong>
          <span className="muted"> · 0–48 h forecast from the departure hour</span>
        </div>
        <div className="forecast-actions">
          <div className="segmented small" role="radiogroup" aria-label="Heatmap metric">
            {METRIC_ORDER.map((key) => (
              <button
                type="button"
                key={key}
                role="radio"
                aria-checked={metric === key}
                className={metric === key ? 'active' : ''}
                onClick={() => onMetric(key)}
              >
                {METRICS[key].label}
              </button>
            ))}
          </div>
          <button type="button" className="ghost" onClick={onToggleVisible}>
            {visible ? 'Hide heatmap' : 'Show heatmap'}
          </button>
        </div>
      </div>

      <div className="forecast-slider-row">
        <button
          type="button"
          className="play-btn"
          onClick={onTogglePlay}
          disabled={!heatmap}
          aria-label={playing ? 'Pause' : 'Play forecast'}
          title={playing ? 'Pause' : 'Play forecast'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <div className="slider-wrap">
          <input
            type="range"
            min={0}
            max={hours}
            step={0.25}
            value={hour}
            disabled={!heatmap}
            onChange={(event) => onHour(Number(event.target.value))}
            aria-label="Forecast hour"
            aria-valuetext={`${formatHourOffset(hour)}, ${formatDayTime(currentMs)}`}
          />
          <div className="slider-marks" aria-hidden="true">
            <span className="depart-mark" style={{ left: percent(plan.departure_time) }} title={`Departure ${formatTime(plan.departure_time)}`} />
            {plan.routes.map((route, index) => (
              <span
                key={route.id}
                className="arrival-mark"
                style={{ left: percent(route.arrival_time), background: routeColor(index) }}
                title={`${route.name} arrives ${formatTime(route.arrival_time)}`}
              />
            ))}
          </div>
          <div className="slider-scale" aria-hidden="true">
            <span>0 h</span>
            <span>12 h</span>
            <span>24 h</span>
            <span>36 h</span>
            <span>48 h</span>
          </div>
        </div>
        <div className="time-readout">
          <div className="time-main">{formatDayTime(currentMs)}</div>
          <div className="muted small">{formatHourOffset(hour)} from departure hour</div>
        </div>
      </div>

      <div className="forecast-footer">
        <Legend spec={spec} />
        <div className="muted small forecast-status" aria-live="polite">
          {loading
            ? 'Loading the 48-hour corridor forecast…'
            : error
              ? `Heatmap unavailable: ${error}`
              : heatmap
                ? `${heatmap.points.length} forecast cells blended across the corridor · 🚚 markers show where each route's truck is at the selected time`
                : ''}
        </div>
      </div>
    </div>
  );
}
