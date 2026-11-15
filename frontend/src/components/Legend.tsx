import { cssGradient, type MetricSpec } from '../lib/heatmap';

export function Legend({ spec }: { spec: MetricSpec }) {
  return (
    <div className="legend" aria-label={`${spec.label} legend`}>
      <div className="legend-title">
        {spec.label}
        {spec.unit ? <span className="muted"> ({spec.unit})</span> : null}
      </div>
      <div className="legend-bar" style={{ background: cssGradient(spec) }} />
      <div className="legend-ticks">
        {spec.ticks.map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
      </div>
    </div>
  );
}
