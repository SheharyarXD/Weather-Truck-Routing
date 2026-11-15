import L from 'leaflet';

import { buildLut, type MetricSpec } from '../../lib/heatmap';

export interface HeatData {
  points: { lat: number; lng: number }[];
  /** One hourly series per point. */
  values: Float32Array[];
  hoursCount: number;
}

interface HeatCanvasOptions {
  /** Pixel size of one interpolation cell; the result is upscaled with bilinear filtering. */
  cellSize?: number;
  /** Number of nearest sample points blended per cell (inverse-distance weighting). */
  neighbors?: number;
  opacity?: number;
  pane?: string;
}

/**
 * Smooth weather heatmap rendered on a canvas.
 *
 * The expensive part (which sample points influence which screen cell, and by
 * how much) only depends on the map view, so it is computed once per move/zoom.
 * Changing the forecast hour or metric only re-blends precomputed weights, which
 * keeps slider scrubbing and playback at 60 fps.
 */
export class HeatCanvasLayer extends L.Layer {
  private canvas: HTMLCanvasElement | null = null;
  private offscreen: HTMLCanvasElement = document.createElement('canvas');
  private readonly cellSize: number;
  private readonly neighbors: number;
  private readonly paneName: string;
  private opacity: number;

  private data: HeatData | null = null;
  private spec: MetricSpec | null = null;
  private hour = 0;

  private cols = 0;
  private rows = 0;
  private k = 0;
  private neighborIndex = new Int32Array(0);
  private neighborWeight = new Float32Array(0);
  private falloff = new Float32Array(0);
  private image: ImageData | null = null;
  private weightsValid = false;
  private pointsKey = '';
  private frame = 0;
  private bounds: L.LatLngBounds | null = null;
  private lutCache = new Map<string, Uint8ClampedArray>();

  constructor(options: HeatCanvasOptions = {}) {
    super();
    this.cellSize = options.cellSize ?? 7;
    this.neighbors = options.neighbors ?? 8;
    this.opacity = options.opacity ?? 0.78;
    this.paneName = options.pane ?? 'overlayPane';
  }

  onAdd(map: L.Map): this {
    const canvas = L.DomUtil.create('canvas', 'heat-canvas leaflet-zoom-animated') as HTMLCanvasElement;
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
    const pane = map.getPane(this.paneName) ?? map.getPanes().overlayPane;
    pane.appendChild(canvas);
    this.canvas = canvas;
    map.on('moveend zoomend resize viewreset', this.reset, this);
    if (map.options.zoomAnimation && L.Browser.any3d) {
      map.on('zoomanim', this.animateZoom as L.LeafletEventHandlerFn, this);
    }
    this.reset();
    return this;
  }

  onRemove(map: L.Map): this {
    map.off('moveend zoomend resize viewreset', this.reset, this);
    map.off('zoomanim', this.animateZoom as L.LeafletEventHandlerFn, this);
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.canvas?.remove();
    this.canvas = null;
    return this;
  }

  setData(data: HeatData | null): void {
    const key = data ? `${data.points.length}:${data.points[0]?.lat},${data.points[0]?.lng}` : '';
    if (key !== this.pointsKey) {
      this.pointsKey = key;
      this.weightsValid = false;
    }
    this.data = data;
    this.schedule();
  }

  setMetric(spec: MetricSpec): void {
    this.spec = spec;
    this.schedule();
  }

  setHour(hour: number): void {
    if (hour === this.hour) return;
    this.hour = hour;
    this.schedule();
  }

  setOpacity(opacity: number): void {
    this.opacity = opacity;
    this.schedule();
  }

  private reset = (): void => {
    const map = this._map;
    const canvas = this.canvas;
    if (!map || !canvas) return;
    const size = map.getSize();
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
    canvas.width = size.x;
    canvas.height = size.y;
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;
    this.bounds = map.getBounds();
    this.cols = Math.max(1, Math.ceil(size.x / this.cellSize));
    this.rows = Math.max(1, Math.ceil(size.y / this.cellSize));
    this.offscreen.width = this.cols;
    this.offscreen.height = this.rows;
    this.image = null;
    this.weightsValid = false;
    this.schedule();
  };

  private animateZoom = (event: L.ZoomAnimEvent): void => {
    const map = this._map as L.Map & {
      _latLngBoundsToNewLayerBounds?: (bounds: L.LatLngBounds, zoom: number, center: L.LatLng) => L.Bounds;
    };
    const canvas = this.canvas;
    if (!map || !canvas || !this.bounds || !map._latLngBoundsToNewLayerBounds) return;
    const scale = map.getZoomScale(event.zoom);
    const offset = map._latLngBoundsToNewLayerBounds(this.bounds, event.zoom, event.center).min;
    if (offset) L.DomUtil.setTransform(canvas, offset, scale);
  };

  private schedule(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  private computeWeights(): void {
    const map = this._map;
    const data = this.data;
    if (!map || !data) return;
    const n = data.points.length;
    const k = Math.min(this.neighbors, n);
    this.k = k;
    const px = new Float32Array(n);
    const py = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const p = map.latLngToContainerPoint([data.points[i].lat, data.points[i].lng]);
      px[i] = p.x;
      py[i] = p.y;
    }

    // Typical grid spacing in pixels (median nearest-neighbour distance of a sample).
    const sampleCount = Math.min(n, 48);
    const nearestDistances: number[] = [];
    for (let s = 0; s < sampleCount; s++) {
      const i = Math.floor((s / sampleCount) * n);
      let best = Infinity;
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const d2 = (px[j] - px[i]) ** 2 + (py[j] - py[i]) ** 2;
        if (d2 < best) best = d2;
      }
      if (best < Infinity) nearestDistances.push(Math.sqrt(best));
    }
    nearestDistances.sort((a, b) => a - b);
    const spacing = nearestDistances.length
      ? Math.max(nearestDistances[Math.floor(nearestDistances.length / 2)], 2)
      : 40;
    const inner = spacing * 1.3;
    const outer = spacing * 2.4;
    const epsilon = (spacing * 0.2) ** 2;

    const cols = this.cols;
    const rows = this.rows;
    const cells = cols * rows;
    this.neighborIndex = new Int32Array(cells * k);
    this.neighborWeight = new Float32Array(cells * k);
    this.falloff = new Float32Array(cells);

    const bestD = new Float64Array(k);
    const bestI = new Int32Array(k);
    for (let r = 0; r < rows; r++) {
      const cy = (r + 0.5) * this.cellSize;
      for (let c = 0; c < cols; c++) {
        const cx = (c + 0.5) * this.cellSize;
        let count = 0;
        for (let i = 0; i < n; i++) {
          const dx = px[i] - cx;
          const dy = py[i] - cy;
          const d2 = dx * dx + dy * dy;
          if (count < k) {
            let pos = count++;
            while (pos > 0 && bestD[pos - 1] > d2) {
              bestD[pos] = bestD[pos - 1];
              bestI[pos] = bestI[pos - 1];
              pos--;
            }
            bestD[pos] = d2;
            bestI[pos] = i;
          } else if (d2 < bestD[k - 1]) {
            let pos = k - 1;
            while (pos > 0 && bestD[pos - 1] > d2) {
              bestD[pos] = bestD[pos - 1];
              bestI[pos] = bestI[pos - 1];
              pos--;
            }
            bestD[pos] = d2;
            bestI[pos] = i;
          }
        }
        const cell = r * cols + c;
        const nearest = Math.sqrt(bestD[0]);
        let f = nearest <= inner ? 1 : nearest >= outer ? 0 : 1 - (nearest - inner) / (outer - inner);
        f = f * f * (3 - 2 * f); // smoothstep for a soft corridor edge
        this.falloff[cell] = f;
        if (f > 0) {
          const base = cell * k;
          for (let j = 0; j < count; j++) {
            this.neighborIndex[base + j] = bestI[j];
            this.neighborWeight[base + j] = 1 / (bestD[j] + epsilon);
          }
        }
      }
    }
    this.weightsValid = true;
  }

  private lutFor(spec: MetricSpec): Uint8ClampedArray {
    let lut = this.lutCache.get(spec.key);
    if (!lut) {
      lut = buildLut(spec);
      this.lutCache.set(spec.key, lut);
    }
    return lut;
  }

  private draw(): void {
    const map = this._map;
    const canvas = this.canvas;
    if (!map || !canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const data = this.data;
    const spec = this.spec;
    if (!data || !spec || data.points.length === 0 || data.hoursCount === 0) return;
    if (!this.weightsValid) this.computeWeights();

    const cols = this.cols;
    const rows = this.rows;
    const cells = cols * rows;
    const k = this.k;
    if (!this.image || this.image.width !== cols || this.image.height !== rows) {
      this.image = new ImageData(cols, rows);
    }
    const buf = this.image.data;
    const lut = this.lutFor(spec);

    const maxHour = data.hoursCount - 1;
    const h = Math.min(Math.max(this.hour, 0), maxHour);
    const h0 = Math.floor(h);
    const h1 = Math.min(h0 + 1, maxHour);
    const t = h - h0;
    const [lo, hi] = spec.domain;
    const span = hi - lo || 1;
    const floor = spec.alphaFloor;
    const opacity = this.opacity;
    const values = data.values;
    const neighborIndex = this.neighborIndex;
    const neighborWeight = this.neighborWeight;
    const falloff = this.falloff;

    for (let cell = 0; cell < cells; cell++) {
      const f = falloff[cell];
      const o = cell * 4;
      if (f <= 0) {
        buf[o + 3] = 0;
        continue;
      }
      let numerator = 0;
      let denominator = 0;
      const base = cell * k;
      for (let j = 0; j < k; j++) {
        const w = neighborWeight[base + j];
        if (w === 0) continue;
        const series = values[neighborIndex[base + j]];
        const v = series[h0] + (series[h1] - series[h0]) * t;
        numerator += w * v;
        denominator += w;
      }
      const value = denominator > 0 ? numerator / denominator : lo;
      let tt = (value - lo) / span;
      tt = tt < 0 ? 0 : tt > 1 ? 1 : tt;
      const ci = (tt * 255) | 0;
      buf[o] = lut[ci * 3];
      buf[o + 1] = lut[ci * 3 + 1];
      buf[o + 2] = lut[ci * 3 + 2];
      buf[o + 3] = (opacity * f * (floor + (1 - floor) * Math.pow(tt, 0.6)) * 255) | 0;
    }

    const offCtx = this.offscreen.getContext('2d');
    if (!offCtx) return;
    offCtx.putImageData(this.image, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(this.offscreen, 0, 0, cols * this.cellSize, rows * this.cellSize);
  }
}
