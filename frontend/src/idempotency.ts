import { useRef } from "react";

import { newKey } from "./api/client";

/**
 * One Idempotency-Key per intent. The key stays the same while the request is unchanged, so
 * a retry after a timeout cannot create a second payment, and changes when the request does.
 */
export function useIdempotencyKey(fingerprint: string): string {
  const held = useRef<{ fingerprint: string; key: string } | null>(null);
  if (held.current === null || held.current.fingerprint !== fingerprint) {
    held.current = { fingerprint, key: newKey() };
  }
  return held.current.key;
}
