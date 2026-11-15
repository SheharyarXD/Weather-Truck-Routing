import { useEffect, useId, useRef, useState } from 'react';

import { geocodeSuggest } from '../api/client';
import type { Place } from '../types';

export interface PlaceValue {
  text: string;
  place: Place | null;
}

interface Props {
  label: string;
  value: PlaceValue;
  onChange: (value: PlaceValue) => void;
  placeholder?: string;
  required?: boolean;
}

/** Text input with debounced geocoding suggestions. Free text is still accepted. */
export function PlaceInput({ label, value, onChange, placeholder, required }: Props) {
  const inputId = useId();
  const [suggestions, setSuggestions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const abortRef = useRef<AbortController | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const query = value.text.trim();
    if (value.place || query.length < 3) {
      setSuggestions([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const results = await geocodeSuggest(query, controller.signal);
        if (!controller.signal.aborted) {
          setSuggestions(results);
          setOpen(results.length > 0);
          setActive(-1);
        }
      } catch {
        if (!controller.signal.aborted) setSuggestions([]);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [value.text, value.place]);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const choose = (place: Place) => {
    onChange({ text: place.label, place });
    setOpen(false);
    setSuggestions([]);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => (i + 1) % suggestions.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault();
      choose(suggestions[active]);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="field place-field" ref={wrapperRef}>
      <label htmlFor={inputId}>{label}</label>
      <input
        id={inputId}
        type="text"
        autoComplete="off"
        value={value.text}
        placeholder={placeholder}
        required={required}
        onChange={(event) => onChange({ text: event.target.value, place: null })}
        onFocus={() => suggestions.length > 0 && setOpen(true)}
        onKeyDown={onKeyDown}
        aria-autocomplete="list"
        aria-expanded={open}
      />
      {value.place && <span className="place-check" title="Location resolved">✓</span>}
      {open && suggestions.length > 0 && (
        <ul className="suggestions" role="listbox">
          {suggestions.map((place, index) => (
            <li
              key={`${place.lat},${place.lng}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? 'active' : ''}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(place)}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
