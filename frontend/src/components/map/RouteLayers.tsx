import { Polyline, Tooltip } from 'react-leaflet';

import { formatDuration, formatMiles } from '../../lib/format';
import { riskColor } from '../../lib/risk';
import type { Route } from '../../types';

interface Props {
  routes: Route[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/**
 * Non-selected routes are drawn as muted lines; the selected route is drawn as
 * one coloured segment per checkpoint so the risk profile is visible on the map.
 */
export function RouteLayers({ routes, selectedId, onSelect }: Props) {
  const dimmed = routes.filter((route) => route.id !== selectedId);
  const selected = routes.find((route) => route.id === selectedId) ?? null;

  return (
    <>
      {dimmed.map((route) => (
        <Polyline
          key={`${route.id}-dim`}
          positions={route.geometry}
          pathOptions={{ color: '#475569', weight: 5, opacity: 0.5, lineCap: 'round', lineJoin: 'round' }}
          eventHandlers={{ click: () => onSelect(route.id) }}
        >
          <Tooltip sticky>
            <strong>{route.name}</strong> · {formatDuration(route.duration_seconds)} · {formatMiles(route.distance_miles)}
            {route.summary ? ` · max ${route.summary.max_level}` : ''}
          </Tooltip>
        </Polyline>
      ))}
      {selected && (
        <>
          <Polyline
            key={`${selected.id}-casing`}
            positions={selected.geometry}
            interactive={false}
            pathOptions={{ color: '#ffffff', weight: 11, opacity: 0.9, lineCap: 'round', lineJoin: 'round' }}
          />
          {selected.checkpoints
            .filter((cp) => cp.path.length > 1)
            .map((cp) => (
              <Polyline
                key={`${selected.id}-segment-${cp.index}`}
                positions={cp.path}
                interactive={false}
                pathOptions={{
                  color: riskColor(cp.risk?.overall),
                  weight: 7,
                  opacity: 0.95,
                  lineCap: 'round',
                  lineJoin: 'round',
                }}
              />
            ))}
        </>
      )}
    </>
  );
}
