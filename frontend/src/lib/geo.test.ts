import { describe, expect, it } from 'vitest';

import type { Checkpoint, Route } from '../types';
import { fastDistanceKm, labelPositions, pointAlongPath, positionAtHour, routeBounds } from './geo';

function checkpoint(index: number, lat: number, lng: number, hours: number, path: [number, number][]): Checkpoint {
  return {
    index,
    mile: index * 50,
    segment_miles: 50,
    lat,
    lng,
    eta: '',
    hours_from_departure: hours,
    is_destination: false,
    path,
    weather: null,
    risk: null,
  };
}

function route(id: string, lat: number): Route {
  const checkpoints = [
    checkpoint(0, lat, -105, 0, [
      [lat, -105],
      [lat, -104],
    ]),
    checkpoint(1, lat, -104, 1, [
      [lat, -104],
      [lat, -103],
    ]),
    checkpoint(2, lat, -103, 3, [[lat, -103]]),
  ];
  return {
    id,
    name: `Route ${id}`,
    source: 'test',
    major_roads: [],
    distance_miles: 100,
    duration_seconds: 3 * 3600,
    departure_time: '',
    arrival_time: '',
    geometry: [
      [lat, -105],
      [lat, -104],
      [lat, -103],
    ],
    checkpoints,
    summary: {
      miles_by_level: { Low: 100, Moderate: 0, High: 0, Severe: 0, 'No Travel': 0 },
      no_travel_miles: 0,
      severe_miles: 0,
      high_miles: 0,
      avg_risk: 0,
      max_level: 'Low',
      worst_checkpoint_index: 0,
      travelable: true,
    },
    rank: 1,
    recommended: true,
  };
}

describe('geo helpers', () => {
  it('measures short distances', () => {
    expect(fastDistanceKm([40, -105], [40, -104])).toBeCloseTo(85.2, 0);
    expect(fastDistanceKm([40, -105], [41, -105])).toBeCloseTo(111.2, 0);
  });

  it('interpolates along a path', () => {
    const path: [number, number][] = [
      [40, -105],
      [40, -104],
      [40, -103],
    ];
    expect(pointAlongPath(path, 0)).toEqual([40, -105]);
    expect(pointAlongPath(path, 1)).toEqual([40, -103]);
    const [lat, lng] = pointAlongPath(path, 0.5);
    expect(lat).toBeCloseTo(40, 6);
    expect(lng).toBeCloseTo(-104, 6);
  });

  it('positions the truck by elapsed time', () => {
    const r = route('A', 40);
    expect(positionAtHour(r, -0.1)).toBeNull();
    expect(positionAtHour(r, 3.1)).toBeNull();
    expect(positionAtHour(r, 0)).toEqual([40, -105]);
    const half = positionAtHour(r, 0.5)!;
    expect(half[1]).toBeCloseTo(-104.5, 6);
    // Second leg is slower (2 h for the same distance): 2 h in -> halfway through it.
    const later = positionAtHour(r, 2)!;
    expect(later[1]).toBeCloseTo(-103.5, 6);
    expect(positionAtHour(r, 3)).toEqual([40, -103]);
  });

  it('computes bounds and picks divergent label positions', () => {
    const a = route('A', 40);
    const b = route('B', 41);
    expect(routeBounds([a, b])).toEqual([
      [40, -105],
      [41, -103],
    ]);
    const labels = labelPositions([a, b]);
    expect(Object.keys(labels).sort()).toEqual(['A', 'B']);
    expect(labels.A[0]).toBe(40);
    expect(labels.B[0]).toBe(41);
  });
});
