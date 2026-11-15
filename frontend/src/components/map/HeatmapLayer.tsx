import { useEffect, useMemo, useRef } from 'react';
import { useMap } from 'react-leaflet';

import { METRICS, metricSeries } from '../../lib/heatmap';
import type { HeatmapMetric, HeatmapResponse } from '../../types';
import { HeatCanvasLayer, type HeatData } from './HeatCanvasLayer';

interface Props {
  data: HeatmapResponse | null;
  metric: HeatmapMetric;
  hour: number;
  visible: boolean;
  opacity?: number;
}

export const HEATMAP_PANE = 'heatmap';

export function HeatmapLayer({ data, metric, hour, visible, opacity = 0.78 }: Props) {
  const map = useMap();
  const layerRef = useRef<HeatCanvasLayer | null>(null);

  useEffect(() => {
    if (!map.getPane(HEATMAP_PANE)) {
      const pane = map.createPane(HEATMAP_PANE);
      pane.style.zIndex = '350'; // above tiles (200), below vector overlays (400)
      pane.style.pointerEvents = 'none';
    }
    const layer = new HeatCanvasLayer({ opacity, pane: HEATMAP_PANE });
    layer.addTo(map);
    layerRef.current = layer;
    return () => {
      layer.remove();
      layerRef.current = null;
    };
    // The layer is created once per map instance; props are pushed through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  const heatData = useMemo<HeatData | null>(() => {
    if (!data || data.points.length === 0) return null;
    return {
      points: data.points.map((p) => ({ lat: p.lat, lng: p.lng })),
      values: data.points.map((p) => Float32Array.from(metricSeries(p, metric))),
      hoursCount: data.times.length,
    };
  }, [data, metric]);

  useEffect(() => {
    layerRef.current?.setMetric(METRICS[metric]);
  }, [metric]);

  useEffect(() => {
    layerRef.current?.setData(visible ? heatData : null);
  }, [heatData, visible]);

  useEffect(() => {
    layerRef.current?.setHour(hour);
  }, [hour]);

  useEffect(() => {
    layerRef.current?.setOpacity(opacity);
  }, [opacity]);

  return null;
}
