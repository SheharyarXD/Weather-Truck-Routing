import L from 'leaflet';
import { useEffect } from 'react';
import { MapContainer, Marker, TileLayer, Tooltip, ZoomControl, useMap } from 'react-leaflet';

import { routeBounds } from '../../lib/geo';
import type { HeatmapMetric, HeatmapResponse, Place, PlanResponse } from '../../types';
import { CheckpointMarkers } from './CheckpointMarkers';
import { HeatmapLayer } from './HeatmapLayer';
import { RouteLabels } from './RouteLabels';
import { RouteLayers } from './RouteLayers';
import { TruckMarkers } from './TruckMarkers';

export interface Focus {
  routeId: string;
  index: number;
}

interface Props {
  plan: PlanResponse | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  heatmap: HeatmapResponse | null;
  metric: HeatmapMetric;
  hour: number;
  showHeatmap: boolean;
  focus: Focus | null;
}

const US_CENTER: [number, number] = [39.5, -98.35];

function FitToPlan({ plan }: { plan: PlanResponse | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan || plan.routes.length === 0) return;
    map.fitBounds(routeBounds(plan.routes), { padding: [56, 56], maxZoom: 11 });
  }, [map, plan]);
  return null;
}

function FlyToFocus({ plan, focus }: { plan: PlanResponse | null; focus: Focus | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan || !focus) return;
    const route = plan.routes.find((r) => r.id === focus.routeId);
    const checkpoint = route?.checkpoints.find((cp) => cp.index === focus.index);
    if (!checkpoint) return;
    map.flyTo([checkpoint.lat, checkpoint.lng], Math.max(map.getZoom(), 9), { duration: 0.7 });
  }, [map, plan, focus]);
  return null;
}

const pinIcon = (kind: 'origin' | 'destination') =>
  L.divIcon({
    className: 'pin-wrap',
    html: `<div class="pin pin-${kind}">${kind === 'origin' ? 'A' : 'B'}</div>`,
    iconSize: [28, 36],
    iconAnchor: [14, 34],
    tooltipAnchor: [0, -30],
  });

const ORIGIN_ICON = pinIcon('origin');
const DESTINATION_ICON = pinIcon('destination');

function EndpointMarkers({ origin, destination }: { origin: Place; destination: Place }) {
  return (
    <>
      <Marker position={[origin.lat, origin.lng]} icon={ORIGIN_ICON} zIndexOffset={2000}>
        <Tooltip direction="top">Origin: {origin.label}</Tooltip>
      </Marker>
      <Marker position={[destination.lat, destination.lng]} icon={DESTINATION_ICON} zIndexOffset={2000}>
        <Tooltip direction="top">Destination: {destination.label}</Tooltip>
      </Marker>
    </>
  );
}

export function MapView({ plan, selectedId, onSelect, heatmap, metric, hour, showHeatmap, focus }: Props) {
  return (
    <MapContainer center={US_CENTER} zoom={4} minZoom={3} zoomControl={false} preferCanvas className="map">
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a> · Weather: <a href="https://open-meteo.com/">Open-Meteo</a> · Routing: <a href="https://project-osrm.org/">OSRM</a>'
        subdomains="abcd"
        maxZoom={19}
      />
      <ZoomControl position="topright" />
      <HeatmapLayer data={heatmap} metric={metric} hour={hour} visible={showHeatmap && !!plan} />
      {plan && (
        <>
          <RouteLayers routes={plan.routes} selectedId={selectedId} onSelect={onSelect} />
          <CheckpointMarkers routes={plan.routes} selectedId={selectedId} onSelect={onSelect} focus={focus} />
          <RouteLabels routes={plan.routes} selectedId={selectedId} onSelect={onSelect} />
          <EndpointMarkers origin={plan.origin} destination={plan.destination} />
          {heatmap && (
            <TruckMarkers
              routes={plan.routes}
              hour={hour}
              heatmapStart={plan.heatmap.start}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          )}
        </>
      )}
      <FitToPlan plan={plan} />
      <FlyToFocus plan={plan} focus={focus} />
    </MapContainer>
  );
}
