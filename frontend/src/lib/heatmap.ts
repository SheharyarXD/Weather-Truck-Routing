import type { HeatmapMetric, HeatmapPoint } from '../types';
import { RISK_LEVELS, RISK_RGB, clamp, type RGB } from './risk';

export interface ColorStop {
  t: number;
  color: RGB;
}

export interface MetricSpec {
  key: HeatmapMetric;
  label: string;
  unit: string;
  domain: [number, number];
  stops: ColorStop[];
  ticks: string[];
  /** Minimum opacity multiplier at the bottom of the domain (calm areas stay faintly visible). */
  alphaFloor: number;
  format: (value: number) => string;
}

export const METRICS: Record<HeatmapMetric, MetricSpec> = {
  risk: {
    key: 'risk',
    label: 'Risk',
    unit: '',
    domain: [0, 4],
    stops: RISK_LEVELS.map((level, i) => ({ t: i / 4, color: RISK_RGB[level] })),
    ticks: ['Low', 'Moderate', 'High', 'Severe', 'No Travel'],
    alphaFloor: 0.22,
    format: (v) => RISK_LEVELS[clamp(Math.round(v), 0, 4)],
  },
  wind: {
    key: 'wind',
    label: 'Wind',
    unit: 'mph',
    domain: [0, 60],
    stops: [
      { t: 0, color: [224, 242, 254] },
      { t: 0.42, color: [59, 130, 246] },
      { t: 0.75, color: [147, 51, 234] },
      { t: 1, color: [190, 24, 93] },
    ],
    ticks: ['0', '15', '30', '45', '60+'],
    alphaFloor: 0.15,
    format: (v) => `${v.toFixed(0)} mph`,
  },
  rain: {
    key: 'rain',
    label: 'Rain',
    unit: 'in/hr',
    domain: [0, 1],
    stops: [
      { t: 0, color: [236, 253, 245] },
      { t: 0.25, color: [52, 211, 153] },
      { t: 0.6, color: [37, 99, 235] },
      { t: 1, color: [30, 27, 75] },
    ],
    ticks: ['0', '0.25', '0.5', '0.75', '1.0+'],
    alphaFloor: 0.12,
    format: (v) => `${v.toFixed(2)} in/hr`,
  },
  snow: {
    key: 'snow',
    label: 'Snow',
    unit: 'in/hr',
    domain: [0, 3],
    stops: [
      { t: 0, color: [240, 249, 255] },
      { t: 0.33, color: [125, 211, 252] },
      { t: 0.66, color: [99, 102, 241] },
      { t: 1, color: [76, 29, 149] },
    ],
    ticks: ['0', '0.75', '1.5', '2.25', '3.0+'],
    alphaFloor: 0.12,
    format: (v) => `${v.toFixed(1)} in/hr`,
  },
  temp: {
    key: 'temp',
    label: 'Temp',
    unit: '°F',
    domain: [-10, 100],
    stops: [
      { t: 0, color: [49, 46, 129] },
      { t: 0.3, color: [59, 130, 246] },
      { t: 0.5, color: [226, 232, 240] },
      { t: 0.75, color: [249, 115, 22] },
      { t: 1, color: [185, 28, 28] },
    ],
    ticks: ['-10', '18', '45', '73', '100'],
    alphaFloor: 0.45,
    format: (v) => `${v.toFixed(0)} °F`,
  },
};

export const METRIC_ORDER: HeatmapMetric[] = ['risk', 'wind', 'rain', 'snow', 'temp'];

export function normalize(spec: MetricSpec, value: number): number {
  const [lo, hi] = spec.domain;
  return clamp((value - lo) / (hi - lo), 0, 1);
}

export function colorAtT(spec: MetricSpec, t: number): RGB {
  const stops = spec.stops;
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i].t) {
      const a = stops[i - 1];
      const b = stops[i];
      const f = (t - a.t) / (b.t - a.t || 1);
      return [
        a.color[0] + (b.color[0] - a.color[0]) * f,
        a.color[1] + (b.color[1] - a.color[1]) * f,
        a.color[2] + (b.color[2] - a.color[2]) * f,
      ];
    }
  }
  return stops[stops.length - 1].color;
}

export function colorAt(spec: MetricSpec, value: number): RGB {
  return colorAtT(spec, normalize(spec, value));
}

/** 256-entry RGB lookup table for fast per-pixel colouring. */
export function buildLut(spec: MetricSpec): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = colorAtT(spec, i / 255);
    lut[i * 3] = r;
    lut[i * 3 + 1] = g;
    lut[i * 3 + 2] = b;
  }
  return lut;
}

export function cssGradient(spec: MetricSpec): string {
  return `linear-gradient(90deg, ${spec.stops
    .map((s) => `rgb(${s.color.map(Math.round).join(',')}) ${Math.round(s.t * 100)}%`)
    .join(', ')})`;
}

export function metricSeries(point: HeatmapPoint, metric: HeatmapMetric): number[] {
  return point[metric];
}

/** Linear interpolation of an hourly series at a fractional hour (clamped to the series). */
export function sampleAtHour(values: ArrayLike<number>, hour: number): number {
  const n = values.length;
  if (n === 0) return 0;
  const h = clamp(hour, 0, n - 1);
  const i = Math.floor(h);
  const j = Math.min(i + 1, n - 1);
  const t = h - i;
  return values[i] + (values[j] - values[i]) * t;
}
