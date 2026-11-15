export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return `${hours}h ${String(rest).padStart(2, '0')}m`;
}

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
const dayTimeFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

export const formatTime = (value: string | number | Date): string => timeFormat.format(new Date(value));
export const formatDayTime = (value: string | number | Date): string => dayTimeFormat.format(new Date(value));
export const formatDateTime = (value: string | number | Date): string => dateTimeFormat.format(new Date(value));

export function formatMiles(miles: number): string {
  return `${Math.round(miles).toLocaleString()} mi`;
}

export function formatNumber(value: number, digits = 0): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatHourOffset(hours: number): string {
  const sign = hours < 0 ? '-' : '+';
  const abs = Math.abs(hours);
  const whole = Math.floor(abs);
  const minutes = Math.round((abs - whole) * 60);
  return minutes ? `${sign}${whole}h ${String(minutes).padStart(2, '0')}m` : `${sign}${whole}h`;
}

/** Value for an ``<input type="datetime-local">`` in the browser's local time. */
export function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** One hour from now, rounded up to the next quarter hour. */
export function defaultDeparture(): Date {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(Math.ceil(date.getMinutes() / 15) * 15, 0, 0);
  return date;
}
