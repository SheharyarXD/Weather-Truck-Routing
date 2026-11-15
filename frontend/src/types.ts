export type RiskLevel = 'Low' | 'Moderate' | 'High' | 'Severe' | 'No Travel';

export type LatLng = [number, number];

export interface Place {
  label: string;
  lat: number;
  lng: number;
}

export interface Weather {
  forecast_time: string;
  temp_f: number;
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  weather_code: number | null;
  description: string;
}

export interface Risk {
  wind: RiskLevel;
  rain: RiskLevel;
  snow: RiskLevel;
  overall: RiskLevel;
  score: number;
  factors: string[];
}

export interface Checkpoint {
  index: number;
  mile: number;
  segment_miles: number;
  lat: number;
  lng: number;
  eta: string;
  hours_from_departure: number;
  is_destination: boolean;
  path: LatLng[];
  weather: Weather | null;
  risk: Risk | null;
}

export interface RouteSummary {
  miles_by_level: Record<RiskLevel, number>;
  no_travel_miles: number;
  severe_miles: number;
  high_miles: number;
  avg_risk: number;
  max_level: RiskLevel;
  worst_checkpoint_index: number | null;
  travelable: boolean;
}

export interface Route {
  id: string;
  name: string;
  source: string;
  major_roads: string[];
  distance_miles: number;
  duration_seconds: number;
  departure_time: string;
  arrival_time: string;
  geometry: LatLng[];
  checkpoints: Checkpoint[];
  summary: RouteSummary;
  rank: number;
  recommended: boolean;
}

export interface Recommendation {
  route_id: string;
  reasons: string[];
  warning: string | null;
  criteria: string[];
}

export interface PlanResponse {
  origin: Place;
  destination: Place;
  departure_time: string;
  load_weight_lb: number;
  sample_interval_miles: number;
  routes: Route[];
  recommendation: Recommendation;
  risk_levels: RiskLevel[];
  heatmap: { start: string; hours: number; points: LatLng[] };
  generated_at: string;
}

export type SampleInterval = 10 | 25 | 50;

export interface PlanRequest {
  origin: string | Place;
  destination: string | Place;
  departure_time: string;
  load_weight_lb: number;
  sample_interval_miles: SampleInterval;
}

export type HeatmapMetric = 'risk' | 'wind' | 'rain' | 'snow' | 'temp';

export interface HeatmapPoint {
  lat: number;
  lng: number;
  risk: number[];
  wind: number[];
  gust: number[];
  rain: number[];
  snow: number[];
  temp: number[];
}

export interface HeatmapRequest {
  points: LatLng[];
  start: string;
  hours: number;
  load_weight_lb: number;
}

export interface HeatmapResponse {
  start: string;
  hours: number;
  times: string[];
  load_weight_lb: number;
  points: HeatmapPoint[];
}
