import { formatDateTime, formatDuration, formatMiles } from '../lib/format';
import type { PlanResponse } from '../types';

interface Props {
  plan: PlanResponse;
  onSelect: (id: string) => void;
}

export function RecommendationPanel({ plan, onSelect }: Props) {
  const route = plan.routes.find((r) => r.id === plan.recommendation.route_id);
  if (!route) return null;
  const { reasons, warning, criteria } = plan.recommendation;
  const unsafe = !route.summary.travelable;

  return (
    <section className={`panel recommendation${unsafe ? ' unsafe' : ''}`}>
      <div className="panel-heading">
        <span className="eyebrow">{unsafe ? 'Least bad option' : 'Recommended route'}</span>
        <button type="button" className="link" onClick={() => onSelect(route.id)}>
          Show on map
        </button>
      </div>
      <h2>
        {route.name}
        {route.major_roads.length > 0 && <span className="via"> via {route.major_roads.join(' · ')}</span>}
      </h2>
      <div className="stat-row">
        <div>
          <div className="stat-value">{formatDuration(route.duration_seconds)}</div>
          <div className="stat-label">drive time</div>
        </div>
        <div>
          <div className="stat-value">{formatMiles(route.distance_miles)}</div>
          <div className="stat-label">distance</div>
        </div>
        <div>
          <div className="stat-value">{formatDateTime(route.arrival_time)}</div>
          <div className="stat-label">arrival (local time)</div>
        </div>
      </div>
      <ul className="reasons">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {warning && <div className="alert alert-warning">{warning}</div>}
      <details className="criteria">
        <summary>How routes are ranked</summary>
        <ol>
          {criteria.map((criterion) => (
            <li key={criterion}>{criterion}</li>
          ))}
        </ol>
        <p className="muted small">
          Each checkpoint's weather is taken at the truck's ETA there and applies to the stretch until the next
          checkpoint. Wind, rain and snow are classified with the assessment thresholds; wind is escalated for
          heavy loads ({plan.load_weight_lb.toLocaleString()} lb entered).
        </p>
      </details>
    </section>
  );
}
