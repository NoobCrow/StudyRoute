"use client";

import { useSyncExternalStore, type ReactNode } from "react";

const subscribe = () => () => {};

/**
 * Renders its children in the browser only. The static export therefore carries no markup that
 * depends on the signed-in person, and React never has to write an inline style attribute into
 * the HTML (the production policy forbids them); styles are applied through the DOM instead.
 */
export function ClientOnly({
  children,
  fallback = null,
}: {
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  return mounted ? children : fallback;
}
