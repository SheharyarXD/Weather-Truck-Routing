import { describe, expect, it } from 'vitest';

import { METRICS, buildLut, colorAt, cssGradient, normalize, sampleAtHour } from './heatmap';
import { RISK_RGB, levelForScore, riskScoreColor } from './risk';

describe('heatmap colour scales', () => {
  it('normalises and clamps to the metric domain', () => {
    expect(normalize(METRICS.wind, -5)).toBe(0);
    expect(normalize(METRICS.wind, 30)).toBeCloseTo(0.5);
    expect(normalize(METRICS.wind, 100)).toBe(1);
  });

  it('maps risk scores onto the risk palette', () => {
    expect(colorAt(METRICS.risk, 0)).toEqual(RISK_RGB.Low);
    expect(colorAt(METRICS.risk, 4)).toEqual(RISK_RGB['No Travel']);
    expect(riskScoreColor(2)).toEqual(RISK_RGB.High);
    const between = riskScoreColor(2.5);
    expect(between[0]).toBeCloseTo((RISK_RGB.High[0] + RISK_RGB.Severe[0]) / 2);
    expect(levelForScore(2.4)).toBe('High');
    expect(levelForScore(2.6)).toBe('Severe');
  });

  it('builds a 256-entry lookup table and a CSS gradient', () => {
    const lut = buildLut(METRICS.rain);
    expect(lut.length).toBe(768);
    expect([lut[0], lut[1], lut[2]]).toEqual(METRICS.rain.stops[0].color);
    expect(cssGradient(METRICS.wind)).toMatch(/^linear-gradient\(90deg, rgb\(/);
  });

  it('interpolates hourly series at fractional hours', () => {
    const series = [0, 10, 20];
    expect(sampleAtHour(series, 0.5)).toBe(5);
    expect(sampleAtHour(series, 1.25)).toBe(12.5);
    expect(sampleAtHour(series, 9)).toBe(20);
    expect(sampleAtHour(series, -1)).toBe(0);
  });
});
