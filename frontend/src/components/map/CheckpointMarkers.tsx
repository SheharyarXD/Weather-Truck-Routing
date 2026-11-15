import { CircleMarker, Popup, Tooltip } from 'react-leaflet';

import { formatDateTime, formatMiles, formatNumber, formatTime } from '../../lib/format';
import { riskColor } from '../../lib/risk';
import type { Checkpoint, Route } from '../../types';

interface Props {
  routes: Route[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  focus: { routeId: string; index: number } | null;
}

function CheckpointPopup({ route, checkpoint }: { route: Route; checkpoint: Checkpoint }) {
  const { weather, risk } = checkpoint;
  return (
    <div className="cp-popup">
      <div className="cp-popup-title">
        <strong>{route.name}</strong>
        <span>
          {checkpoint.is_destination
            ? 'Destination'
            : checkpoint.index === 0
              ? 'Origin'
              : `Mile ${formatNumber(checkpoint.mile)} of ${formatNumber(route.distance_miles)}`}
        </span>
      </div>
      <div className="cp-popup-eta">ETA {formatDateTime(checkpoint.eta)}</div>
      {weather && (
        <>
          <div className="cp-popup-weather">
            {weather.description} · {formatNumber(weather.temp_f)}°F
          </div>
          <dl className="cp-popup-grid">
            <dt>Wind</dt>
            <dd>
              {formatNumber(weather.wind_mph)} mph <span className="muted">(gusts {formatNumber(weather.gust_mph)})</span>
            </dd>
            <dt>Rain</dt>
            <dd>{weather.rain_in_hr.toFixed(2)} in/hr</dd>
            <dt>Snow</dt>
            <dd>{weather.snow_in_hr.toFixed(1)} in/hr</dd>
          </dl>
        </>
      )}
      {risk && (
        <div className="cp-popup-risk">
          <span className="badge" style={{ background: riskColor(risk.overall) }}>
            {risk.overall}
          </span>
          {checkpoint.segment_miles > 0 && (
            <span className="muted"> applies to the next {formatMiles(checkpoint.segment_miles)}</span>
          )}
          <ul>
            {risk.factors.map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function CheckpointMarkers({ routes, selectedId, onSelect, focus }: Props) {
  const focused =
    focus && routes.find((r) => r.id === focus.routeId)?.checkpoints.find((cp) => cp.index === focus.index);

  return (
    <>
      {routes.map((route) => {
        const isSelected = route.id === selectedId;
        return route.checkpoints.map((cp) => {
          const endpoint = cp.index === 0 || cp.is_destination;
          return (
            <CircleMarker
              key={`${route.id}-${cp.index}-${isSelected ? 'sel' : 'dim'}`}
              center={[cp.lat, cp.lng]}
              radius={isSelected ? (endpoint ? 8 : 6) : 4}
              pathOptions={{
                color: '#ffffff',
                weight: isSelected ? 2 : 1,
                opacity: isSelected ? 1 : 0.75,
                fillColor: riskColor(cp.risk?.overall),
                fillOpacity: isSelected ? 1 : 0.7,
              }}
              eventHandlers={{ click: () => onSelect(route.id) }}
            >
              <Tooltip direction="top" offset={[0, -6]} opacity={0.95}>
                {route.name} · Mile {formatNumber(cp.mile)} · ETA {formatTime(cp.eta)} ·{' '}
                <strong>{cp.risk?.overall ?? 'n/a'}</strong>
              </Tooltip>
              <Popup maxWidth={300} autoPanPadding={[40, 40]}>
                <CheckpointPopup route={route} checkpoint={cp} />
              </Popup>
            </CircleMarker>
          );
        });
      })}
      {focused && (
        <CircleMarker
          key={`focus-${focus!.routeId}-${focus!.index}`}
          center={[focused.lat, focused.lng]}
          radius={15}
          interactive={false}
          pathOptions={{ color: '#2563eb', weight: 3, fill: false, opacity: 0.9, dashArray: '4 4' }}
        />
      )}
    </>
  );
}
