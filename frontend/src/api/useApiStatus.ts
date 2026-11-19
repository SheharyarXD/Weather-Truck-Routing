import { useEffect, useState } from 'react';

import { checkHealth } from './client';

export type ApiStatus = 'checking' | 'online' | 'waking' | 'offline';

const SLOW_AFTER_MS = 2500;
const GIVE_UP_AFTER_MS = 120_000;
const ATTEMPT_TIMEOUT_MS = 70_000;
const RETRY_DELAY_MS = 3000;

/**
 * Pings the API as soon as the page loads.
 *
 * Free hosting tiers put the API to sleep when idle and the first request can take
 * up to a minute. Pinging on load wakes it while the driver fills in the form, and
 * the returned status lets the UI explain the delay instead of looking stuck.
 */
export function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>('checking');

  useEffect(() => {
    let cancelled = false;
    let controller: AbortController | null = null;
    const started = Date.now();
    const slowTimer = window.setTimeout(() => {
      if (!cancelled) setStatus((current) => (current === 'checking' ? 'waking' : current));
    }, SLOW_AFTER_MS);

    const run = async () => {
      while (!cancelled && Date.now() - started < GIVE_UP_AFTER_MS) {
        controller = new AbortController();
        const attemptTimer = window.setTimeout(() => controller?.abort(), ATTEMPT_TIMEOUT_MS);
        try {
          await checkHealth(controller.signal);
          if (!cancelled) setStatus('online');
          return;
        } catch {
          await new Promise((resolve) => window.setTimeout(resolve, RETRY_DELAY_MS));
        } finally {
          window.clearTimeout(attemptTimer);
        }
      }
      if (!cancelled) setStatus('offline');
    };
    void run();

    return () => {
      cancelled = true;
      window.clearTimeout(slowTimer);
      controller?.abort();
    };
  }, []);

  return status;
}
