import { useState } from 'react';

import { defaultDeparture, toLocalInputValue } from '../lib/format';
import type { PlanRequest, SampleInterval } from '../types';
import { PlaceInput, type PlaceValue } from './PlaceInput';

interface Props {
  onSubmit: (request: PlanRequest) => void;
  busy: boolean;
}

const LOAD_PRESETS = [20000, 35000, 45000];
const INTERVALS: SampleInterval[] = [10, 25, 50];

const EXAMPLE = {
  origin: { text: 'Denver, Colorado, United States', place: { label: 'Denver, Colorado, United States', lat: 39.7392364, lng: -104.984862 } },
  destination: { text: 'Salt Lake City, Utah, United States', place: { label: 'Salt Lake City, Utah, United States', lat: 40.7596198, lng: -111.886797 } },
};

export function PlanForm({ onSubmit, busy }: Props) {
  const [origin, setOrigin] = useState<PlaceValue>({ text: '', place: null });
  const [destination, setDestination] = useState<PlaceValue>({ text: '', place: null });
  const [departure, setDeparture] = useState(() => toLocalInputValue(defaultDeparture()));
  const [load, setLoad] = useState('35000');
  const [interval, setInterval] = useState<SampleInterval>(25);
  const [validation, setValidation] = useState<string | null>(null);

  const swap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const loadValue = Number(load);
    const departureDate = new Date(departure);
    if (origin.text.trim().length < 2 || destination.text.trim().length < 2) {
      setValidation('Enter both an origin and a destination.');
      return;
    }
    if (Number.isNaN(departureDate.getTime())) {
      setValidation('Enter a valid departure date and time.');
      return;
    }
    if (!Number.isFinite(loadValue) || loadValue < 0) {
      setValidation('Load weight must be a positive number of pounds.');
      return;
    }
    setValidation(null);
    onSubmit({
      origin: origin.place ?? origin.text.trim(),
      destination: destination.place ?? destination.text.trim(),
      departure_time: departureDate.toISOString(),
      load_weight_lb: Math.round(loadValue),
      sample_interval_miles: interval,
    });
  };

  return (
    <form className="plan-form" onSubmit={handleSubmit} noValidate>
      <div className="place-row">
        <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City, address or lat, lon" required />
        <button type="button" className="swap-btn" onClick={swap} title="Swap origin and destination" aria-label="Swap origin and destination">
          ⇅
        </button>
        <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="Where is the load going?" required />
      </div>

      <div className="field-grid">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input id="departure" type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input id="load" type="number" min={0} max={200000} step={500} inputMode="numeric" value={load} onChange={(e) => setLoad(e.target.value)} required />
          <div className="chips">
            {LOAD_PRESETS.map((preset) => (
              <button type="button" key={preset} className={`chip${Number(load) === preset ? ' active' : ''}`} onClick={() => setLoad(String(preset))}>
                {preset.toLocaleString()}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="field">
        <span className="label">Weather checkpoints every</span>
        <div className="segmented" role="radiogroup" aria-label="Sampling interval">
          {INTERVALS.map((option) => (
            <button
              type="button"
              key={option}
              role="radio"
              aria-checked={interval === option}
              className={interval === option ? 'active' : ''}
              onClick={() => setInterval(option)}
            >
              {option} mi
            </button>
          ))}
        </div>
      </div>

      {validation && <div className="alert alert-error">{validation}</div>}

      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? 'Planning…' : 'Plan routes'}
        </button>
        <button
          type="button"
          className="link"
          disabled={busy}
          onClick={() => {
            setOrigin(EXAMPLE.origin);
            setDestination(EXAMPLE.destination);
            setLoad('35000');
          }}
        >
          Use example trip
        </button>
      </div>
    </form>
  );
}
