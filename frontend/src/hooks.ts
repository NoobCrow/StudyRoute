import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api/client";

export interface Loaded<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  reload: () => void;
}

/** Runs an async loader on mount and whenever `deps` change. Ignores stale answers. */
export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[]): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    const id = ++latest.current;
    setLoading(true);
    loaderRef
      .current()
      .then((value) => {
        if (id === latest.current) {
          setData(value);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (id === latest.current) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (id === latest.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Milliseconds since the epoch, refreshed every `intervalMs`. Drives countdowns. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

/** Calls `fn` every `ms` while `active` is true (used for the live tracker). */
export function usePolling(fn: () => void, ms: number, active: boolean): void {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(() => ref.current(), ms);
    return () => window.clearInterval(timer);
  }, [ms, active]);
}
