"use client";

import { useEffect, useSyncExternalStore } from "react";

export interface ChatScope {
  quoteId?: string;
  paymentId?: string;
}

let scope: ChatScope = {};
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((listener) => listener());
}

/** Screens tell the assistant which quote or payment the user is looking at. */
export function useChatScope(next: ChatScope): void {
  const { quoteId, paymentId } = next;
  useEffect(() => {
    scope = { quoteId, paymentId };
    emit();
    return () => {
      scope = {};
      emit();
    };
  }, [quoteId, paymentId]);
}

export function useCurrentChatScope(): ChatScope {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => scope,
  );
}
