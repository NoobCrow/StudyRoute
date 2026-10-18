"use client";

import { useEffect, useEffectEvent } from "react";

/** Calls `fn` every `ms` milliseconds while `active` is true (used while something is in flight). */
export function usePolling(fn: () => void, ms: number, active: boolean): void {
  const tick = useEffectEvent(fn);
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(() => tick(), ms);
    return () => window.clearInterval(timer);
  }, [ms, active]);
}
