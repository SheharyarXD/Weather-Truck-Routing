import type { RiskLevel } from '../types';

export type RGB = [number, number, number];

export const RISK_LEVELS: RiskLevel[] = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'];

export const RISK_RGB: Record<RiskLevel, RGB> = {
  Low: [34, 197, 94],
  Moderate: [234, 179, 8],
  High: [249, 115, 22],
  Severe: [239, 68, 68],
  'No Travel': [126, 34, 206],
};

export const RISK_COLORS = Object.fromEntries(
  RISK_LEVELS.map((level) => [level, `rgb(${RISK_RGB[level].join(',')})`]),
) as Record<RiskLevel, string>;

/** Colours that identify routes A/B/C (labels, truck markers), independent of risk. */
export const ROUTE_COLORS = ['#2563eb', '#0d9488', '#9333ea', '#db2777'];

export const clamp = (value: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, value));

export function riskColor(level: RiskLevel | null | undefined): string {
  return level ? RISK_COLORS[level] : '#9ca3af';
}

export function routeColor(index: number): string {
  return ROUTE_COLORS[index % ROUTE_COLORS.length];
}

/** Continuous colour for a (possibly fractional) risk score in [0, 4]. */
export function riskScoreColor(score: number): RGB {
  const s = clamp(score, 0, 4);
  const i = Math.min(Math.floor(s), 3);
  const t = s - i;
  const a = RISK_RGB[RISK_LEVELS[i]];
  const b = RISK_RGB[RISK_LEVELS[i + 1]];
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

export function levelForScore(score: number): RiskLevel {
  return RISK_LEVELS[clamp(Math.round(score), 0, 4)];
}
