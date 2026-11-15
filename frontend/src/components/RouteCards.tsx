import { formatDuration, formatMiles, formatNumber, formatTime } from '../lib/format';
import { RISK_COLORS, RISK_LEVELS, riskColor, routeColor } from '../lib/risk';
import type { Route, RouteSummary } from '../types';

interface Props {
  routes: Route[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function RiskBar({ summary, total }: { summary: RouteSummary; total: number }) {
  return (
    <div className="risk-bar" role="img" aria-label="Miles per risk level">
      {RISK_LEVELS.map((level) => {
        const miles = summary.miles_by_level[level] ?? 0;
        if (miles <= 0) return null;
        return (
          <span
            key={level}
            style={{ width: `${(miles / Math.max(total, 1)) * 100}%`, background: RISK_COLORS[level] }}
            title={`${level}: ${formatMiles(miles)}`}
          />
        );
      })}
    </div>
  );
}

export function RouteCards({ routes, selectedId, onSelect }: Props) {
  const ordered = [...routes].sort((a, b) => a.rank - b.rank);
  return (
    <section className="panel">
      <div className="panel-heading">
        <span className="eyebrow">Route options</span>
        <span className="muted small">ranked by weather risk, then time</span>
      </div>
      <div className="route-cards">
        {ordered.map((route) => {
          const index = routes.indexOf(route);
          const selected = route.id === selectedId;
          const summary = route.summary;
          return (
            <button
              type="button"
              key={route.id}
              className={`route-card${selected ? ' selected' : ''}${summary.travelable ? '' : ' unsafe'}`}
              onClick={() => onSelect(route.id)}
              aria-pressed={selected}
            >
              <div className="route-card-head">
                <span className="route-id" style={{ background: routeColor(index) }}>
                  {route.id}
                </span>
                <div className="route-card-title">
                  <strong>{route.name}</strong>
                  {route.major_roads.length > 0 && <span className="muted"> via {route.major_roads.join(', ')}</span>}
                </div>
                <span className={`rank-badge${route.recommended ? ' top' : ''}`}>
                  {route.recommended ? 'Recommended' : `#${route.rank}`}
                </span>
              </div>
              <div className="route-card-stats">
                <span>
                  <strong>{formatDuration(route.duration_seconds)}</strong> drive
                </span>
                <span>
                  <strong>{formatMiles(route.distance_miles)}</strong>
                </span>
                <span>
                  arrive <strong>{formatTime(route.arrival_time)}</strong>
                </span>
              </div>
              <RiskBar summary={summary} total={route.distance_miles} />
              <div className="route-card-risk">
                <span>
                  <i className="dot" style={{ background: riskColor('No Travel') }} />
                  No-Travel {formatNumber(summary.no_travel_miles)} mi
                </span>
                <span>
                  <i className="dot" style={{ background: riskColor('Severe') }} />
                  Severe {formatNumber(summary.severe_miles)} mi
                </span>
                <span>
                  <i className="dot" style={{ background: riskColor('High') }} />
                  High {formatNumber(summary.high_miles)} mi
                </span>
                <span title="Distance-weighted average risk score (0 = Low … 4 = No Travel)">
                  avg {summary.avg_risk.toFixed(2)}
                </span>
              </div>
              {!summary.travelable && <div className="unsafe-note">Crosses No-Travel conditions for this load</div>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
