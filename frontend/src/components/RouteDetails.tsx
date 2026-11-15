import { formatMiles, formatNumber, formatTime } from '../lib/format';
import { riskColor } from '../lib/risk';
import type { Route } from '../types';

interface Props {
  route: Route;
  intervalMiles: number;
  focusIndex: number | null;
  onFocusCheckpoint: (index: number) => void;
}

export function RouteDetails({ route, intervalMiles, focusIndex, onFocusCheckpoint }: Props) {
  const worst = route.summary.worst_checkpoint_index;
  return (
    <section className="panel">
      <div className="panel-heading">
        <span className="eyebrow">
          {route.name} checkpoints
        </span>
        <span className="muted small">
          every {intervalMiles} mi · {route.checkpoints.length} points · max {route.summary.max_level}
        </span>
      </div>
      <div className="table-wrap">
        <table className="checkpoints">
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Conditions</th>
              <th className="num">Wind</th>
              <th className="num">Rain</th>
              <th className="num">Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => {
              const level = cp.risk?.overall;
              const classes = [
                cp.index === focusIndex ? 'focused' : '',
                cp.index === worst && level && level !== 'Low' ? 'worst' : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <tr key={cp.index} className={classes} onClick={() => onFocusCheckpoint(cp.index)} title="Show on map">
                  <td>
                    {cp.is_destination ? 'End' : cp.index === 0 ? 'Start' : formatNumber(cp.mile)}
                  </td>
                  <td>{formatTime(cp.eta)}</td>
                  <td className="conditions">
                    {cp.weather ? (
                      <>
                        {cp.weather.description}
                        <span className="muted"> · {formatNumber(cp.weather.temp_f)}°F</span>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="num" style={{ color: cp.risk && cp.risk.wind !== 'Low' ? riskColor(cp.risk.wind) : undefined }}>
                    {cp.weather ? formatNumber(cp.weather.wind_mph) : '—'}
                  </td>
                  <td className="num" style={{ color: cp.risk && cp.risk.rain !== 'Low' ? riskColor(cp.risk.rain) : undefined }}>
                    {cp.weather ? cp.weather.rain_in_hr.toFixed(2) : '—'}
                  </td>
                  <td className="num" style={{ color: cp.risk && cp.risk.snow !== 'Low' ? riskColor(cp.risk.snow) : undefined }}>
                    {cp.weather ? cp.weather.snow_in_hr.toFixed(1) : '—'}
                  </td>
                  <td>
                    {level && (
                      <span className="badge" style={{ background: riskColor(level) }} title={cp.risk?.factors.join('\n')}>
                        {level}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Wind in mph, rain and snow in in/hr. Each row's risk applies to the next {formatMiles(intervalMiles)} of road.
        Click a row to locate it on the map.
      </p>
    </section>
  );
}
