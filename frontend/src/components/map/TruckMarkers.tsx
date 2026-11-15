import L from 'leaflet';
import { Marker, Tooltip } from 'react-leaflet';

import { formatTime } from '../../lib/format';
import { positionAtHour } from '../../lib/geo';
import { routeColor } from '../../lib/risk';
import type { Route } from '../../types';

interface Props {
  routes: Route[];
  /** Hours since the heatmap start hour (the slider value). */
  hour: number;
  heatmapStart: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const iconCache = new Map<string, L.DivIcon>();

function truckIcon(label: string, color: string, selected: boolean): L.DivIcon {
  const key = `${label}|${color}|${selected}`;
  let icon = iconCache.get(key);
  if (!icon) {
    icon = L.divIcon({
      className: 'truck-icon-wrap',
      html: `<div class="truck-icon${selected ? ' selected' : ''}" style="--route-color:${color}"><span class="truck-emoji" aria-hidden="true">🚚</span><span class="truck-label">${label}</span></div>`,
      iconSize: [40, 40],
      iconAnchor: [20, 20],
      tooltipAnchor: [0, -18],
    });
    iconCache.set(key, icon);
  }
  return icon;
}

/** Where each truck would be at the time selected on the forecast slider. */
export function TruckMarkers({ routes, hour, heatmapStart, selectedId, onSelect }: Props) {
  const startMs = new Date(heatmapStart).getTime();
  const currentMs = startMs + hour * 3600 * 1000;
  return (
    <>
      {routes.map((route, index) => {
        const offsetHours = (new Date(route.departure_time).getTime() - startMs) / 3600000;
        const position = positionAtHour(route, hour - offsetHours);
        if (!position) return null;
        const selected = route.id === selectedId;
        return (
          <Marker
            key={route.id}
            position={position}
            icon={truckIcon(route.id, routeColor(index), selected)}
            zIndexOffset={selected ? 1000 : 0}
            eventHandlers={{ click: () => onSelect(route.id) }}
          >
            <Tooltip direction="top">
              {route.name} at {formatTime(currentMs)}
            </Tooltip>
          </Marker>
        );
      })}
    </>
  );
}
