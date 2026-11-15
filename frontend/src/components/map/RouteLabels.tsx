import L from 'leaflet';
import { useMemo } from 'react';
import { Marker } from 'react-leaflet';

import { formatDuration, formatMiles } from '../../lib/format';
import { labelPositions } from '../../lib/geo';
import { riskColor, routeColor } from '../../lib/risk';
import type { Route } from '../../types';

interface Props {
  routes: Route[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Compact route summaries pinned to the map where the routes diverge. */
export function RouteLabels({ routes, selectedId, onSelect }: Props) {
  const positions = useMemo(() => labelPositions(routes), [routes]);

  return (
    <>
      {routes.map((route, index) => {
        const position = positions[route.id];
        if (!position) return null;
        const selected = route.id === selectedId;
        const summary = route.summary;
        const worst = summary ? summary.max_level : null;
        const html = `
          <div class="route-label${selected ? ' selected' : ''}${route.recommended ? ' recommended' : ''}" style="--route-color:${routeColor(index)}">
            <span class="route-label-id">${escapeHtml(route.id)}</span>
            <span class="route-label-body">
              <span class="route-label-line">${formatDuration(route.duration_seconds)} · ${formatMiles(route.distance_miles)}</span>
              <span class="route-label-line muted">${route.recommended ? 'Recommended' : `#${route.rank}`}${
                worst ? ` · <span class="dot" style="background:${riskColor(worst)}"></span>${escapeHtml(worst)}` : ''
              }</span>
            </span>
          </div>`;
        const icon = L.divIcon({ className: 'route-label-wrap', html, iconSize: undefined });
        return (
          <Marker
            key={`${route.id}-${selected ? 'sel' : 'dim'}-${route.rank}`}
            position={position}
            icon={icon}
            zIndexOffset={selected ? 500 : 0}
            eventHandlers={{ click: () => onSelect(route.id) }}
          />
        );
      })}
    </>
  );
}
