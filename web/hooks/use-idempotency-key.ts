"use client";

import { useState } from "react";

import { newKey } from "@/lib/api/client";

/**
 * One Idempotency-Key per intent. The key stays the same while the request is unchanged, so
 * a retry after a timeout cannot create a second payment, and changes when the request does.
 */
export function useIdempotencyKey(fingerprint: string): string {
  const [held, setHeld] = useState(() => ({ fingerprint, key: newKey() }));
  if (held.fingerprint !== fingerprint) {
    const next = { fingerprint, key: newKey() };
    setHeld(next);
    return next.key;
  }
  return held.key;
}
