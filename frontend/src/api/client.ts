import type { HeatmapRequest, HeatmapResponse, Place, PlanRequest, PlanResponse } from '../types';

const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '/api').replace(/\/$/, '');

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(message: string, code: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }

  /** Human-readable message including field-level validation details. */
  describe(): string {
    if (this.details && typeof this.details === 'object' && !Array.isArray(this.details)) {
      const parts = Object.entries(this.details as Record<string, unknown>).map(([field, messages]) => {
        const text = Array.isArray(messages) ? messages.join(' ') : String(messages);
        return `${field.replace(/_/g, ' ')}: ${text}`;
      });
      if (parts.length) return parts.join(' ');
    }
    return this.message;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(init.headers ?? {}) },
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = (body as { error?: { message?: string; code?: string; details?: unknown } } | null)?.error;
    throw new ApiError(
      error?.message ?? `Request failed with status ${response.status}`,
      error?.code ?? 'http_error',
      response.status,
      error?.details,
    );
  }
  return body as T;
}

export function planTrip(body: PlanRequest, signal?: AbortSignal): Promise<PlanResponse> {
  return request<PlanResponse>('/plan/', { method: 'POST', body: JSON.stringify(body), signal });
}

export function fetchHeatmap(body: HeatmapRequest, signal?: AbortSignal): Promise<HeatmapResponse> {
  return request<HeatmapResponse>('/heatmap/', { method: 'POST', body: JSON.stringify(body), signal });
}

export async function geocodeSuggest(query: string, signal?: AbortSignal): Promise<Place[]> {
  const result = await request<{ results: Place[] }>(
    `/geocode/?q=${encodeURIComponent(query)}&limit=6`,
    { signal },
  );
  return result.results;
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.describe();
  if (error instanceof Error) return error.message;
  return 'Something went wrong.';
}
