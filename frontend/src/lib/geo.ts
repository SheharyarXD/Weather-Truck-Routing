import type { LatLng, Route } from '../types';

const KM_PER_DEG_LAT = 111.195;

export function fastDistanceKm(a: LatLng, b: LatLng): number {
  const kx = Math.cos((((a[0] + b[0]) / 2) * Math.PI) / 180);
  const dx = (b[1] - a[1]) * kx * KM_PER_DEG_LAT;
  const dy = (b[0] - a[0]) * KM_PER_DEG_LAT;
  return Math.hypot(dx, dy);
}

/** Point at ``fraction`` (0..1) of a polyline's length. */
export function pointAlongPath(path: LatLng[], fraction: number): LatLng {
  if (path.length === 0) throw new Error('empty path');
  if (path.length === 1) return path[0];
  const cumulative = [0];
  for (let i = 1; i < path.length; i++) {
    cumulative.push(cumulative[i - 1] + fastDistanceKm(path[i - 1], path[i]));
  }
  const total = cumulative[cumulative.length - 1];
  const target = Math.min(Math.max(fraction, 0), 1) * total;
  if (total === 0) return path[0];
  let i = 0;
  while (i < cumulative.length - 2 && cumulative[i + 1] < target) i++;
  const segment = cumulative[i + 1] - cumulative[i];
  const t = segment > 0 ? (target - cumulative[i]) / segment : 0;
  const a = path[i];
  const b = path[i + 1];
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/**
 * Where the truck is ``hoursFromDeparture`` into the trip, interpolating along the
 * checkpoint paths by time. ``null`` before departure or after arrival.
 */
export function positionAtHour(route: Route, hoursFromDeparture: number): LatLng | null {
  const checkpoints = route.checkpoints;
  if (checkpoints.length === 0) return null;
  const last = checkpoints[checkpoints.length - 1];
  if (hoursFromDeparture < 0 || hoursFromDeparture > last.hours_from_departure) return null;
  for (let k = 0; k < checkpoints.length - 1; k++) {
    const current = checkpoints[k];
    const next = checkpoints[k + 1];
    if (hoursFromDeparture <= next.hours_from_departure) {
      const span = next.hours_from_departure - current.hours_from_departure;
      const fraction = span > 0 ? (hoursFromDeparture - current.hours_from_departure) / span : 0;
      if (current.path.length >= 2) return pointAlongPath(current.path, fraction);
      return [current.lat + (next.lat - current.lat) * fraction, current.lng + (next.lng - current.lng) * fraction];
    }
  }
  return [last.lat, last.lng];
}

export function routeBounds(routes: Route[]): [LatLng, LatLng] {
  let minLat = Infinity;
  let minLng = Infinity;
  let maxLat = -Infinity;
  let maxLng = -Infinity;
  for (const route of routes) {
    for (const [lat, lng] of route.geometry) {
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
    }
  }
  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ];
}

function sampled(points: LatLng[], maxPoints: number): LatLng[] {
  const stride = Math.max(1, Math.ceil(points.length / maxPoints));
  const out: LatLng[] = [];
  for (let i = 0; i < points.length; i += stride) out.push(points[i]);
  return out;
}

/**
 * A label anchor per route: the point of that route farthest from every other
 * route, so labels sit where the alternatives actually diverge.
 */
export function labelPositions(routes: Route[]): Record<string, LatLng> {
  const samples = routes.map((route) => sampled(route.geometry, 160));
  const result: Record<string, LatLng> = {};
  routes.forEach((route, index) => {
    const own = samples[index];
    if (own.length === 0) return;
    const others = samples.filter((_, j) => j !== index);
    if (others.length === 0) {
      result[route.id] = own[Math.floor(own.length / 2)];
      return;
    }
    let best = own[Math.floor(own.length / 2)];
    let bestDistance = -1;
    for (const point of own) {
      let nearest = Infinity;
      for (const other of others) {
        for (const candidate of other) {
          const d = fastDistanceKm(point, candidate);
          if (d < nearest) nearest = d;
        }
      }
      if (nearest > bestDistance) {
        bestDistance = nearest;
        best = point;
      }
    }
    if (bestDistance < 1) {
      // Routes overlap almost everywhere: spread labels out along the line instead.
      best = own[Math.floor(((index + 1) / (routes.length + 1)) * (own.length - 1))];
    }
    result[route.id] = best;
  });
  return result;
}
