"use client";

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { get } from "@/lib/api/client";

export interface Loaded<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

interface Options {
  enabled?: boolean;
  /** While a changed path loads, keep showing the answer to the one before, instead of nothing. */
  keepPrevious?: boolean;
  /** Poll every so many milliseconds while this says so (used for the live tracker and KYC review). */
  refetchInterval?: number | false | ((data: unknown) => number | false);
}

/** GET a path through TanStack Query. `null` means "not ready yet": nothing is fetched. */
export function useApi<T>(path: string | null, options: Options = {}): Loaded<T> {
  const query = useQuery<T, Error>({
    queryKey: ["api", path],
    queryFn: () => get<T>(path as string),
    enabled: path !== null && options.enabled !== false,
    placeholderData: options.keepPrevious ? keepPreviousData : undefined,
    refetchInterval: (query) => {
      const interval = options.refetchInterval ?? false;
      return typeof interval === "function" ? interval(query.state.data) : interval;
    },
  });
  const { refetch } = query;
  const reload = useCallback(() => void refetch(), [refetch]);
  return { data: query.data ?? null, error: query.error, loading: query.isLoading, reload };
}

/** Same, for loaders that are not a plain GET. `key` must identify the request. */
export function useLoader<T>(
  key: readonly unknown[],
  loader: () => Promise<T>,
  enabled = true,
): Loaded<T> {
  const query = useQuery<T, Error>({ queryKey: ["loader", ...key], queryFn: loader, enabled });
  const { refetch } = query;
  const reload = useCallback(() => void refetch(), [refetch]);
  return { data: query.data ?? null, error: query.error, loading: query.isLoading, reload };
}

/** Throws away cached answers (after a change the person made) so screens read fresh data. */
export function useInvalidateApi(): () => Promise<void> {
  const client = useQueryClient();
  return useCallback(() => client.invalidateQueries(), [client]);
}
