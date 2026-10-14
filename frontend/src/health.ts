import { get } from "./api/client";
import type { Health } from "./api/types";

let cached: Promise<Health> | null = null;

/** Public status of the API (mode, AI mode and, in the sandbox, the documented demo hints). */
export function loadHealth(): Promise<Health> {
  cached ??= get<Health>("/health", { auth: false }).catch((error: unknown) => {
    cached = null;
    throw error;
  });
  return cached;
}

export function resetHealthCache(): void {
  cached = null;
}
