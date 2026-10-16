"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useCurrentChatScope } from "@/hooks/use-chat-scope";
import { post } from "@/lib/api/client";
import type { ChatResponse, PendingTask } from "@/lib/api/types";

export interface Turn {
  id: number;
  role: "me" | "bot";
  text: string;
  reply?: ChatResponse;
}

interface AssistantState {
  turns: Turn[];
  busy: boolean;
  error: Error | null;
  mode: ChatResponse | null;
  ask: (message: string) => Promise<void>;
}

const AssistantContext = createContext<AssistantState | null>(null);

/** The conversation lives here, so closing the side sheet does not lose it. */
export function AssistantProvider({ children }: { children: ReactNode }) {
  const scope = useCurrentChatScope();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [mode, setMode] = useState<ChatResponse | null>(null);
  const [planQuote, setPlanQuote] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingTask | null>(null);
  const counter = useRef(0);

  const ask = useCallback(
    async (message: string) => {
      const clean = message.trim();
      if (!clean || busy) return;
      setError(null);
      setBusy(true);
      setTurns((t) => [...t, { id: ++counter.current, role: "me", text: clean }]);
      try {
        const context = {
          quote_id: scope.quoteId ?? planQuote,
          payment_id: scope.paymentId ?? null,
          pending,
        };
        const reply = await post<ChatResponse>("/assistant/chat", { message: clean, context });
        setMode(reply);
        if (reply.task?.kind === "payment_plan" && reply.task.status === "ready")
          setPlanQuote(reply.task.quote.quote_id);
        const task = reply.task;
        const waiting =
          task && (task.status === "needs_input" || task.status === "needs_confirmation");
        setPending(
          waiting
            ? ({ kind: task.kind, ...(task as { collected?: object }).collected } as PendingTask)
            : null,
        );
        setTurns((t) => [...t, { id: ++counter.current, role: "bot", text: reply.reply, reply }]);
      } catch (e) {
        setError(e as Error);
      } finally {
        setBusy(false);
      }
    },
    [busy, scope.quoteId, scope.paymentId, planQuote, pending],
  );

  const value = useMemo(() => ({ turns, busy, error, mode, ask }), [turns, busy, error, mode, ask]);
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantState {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside AssistantProvider");
  return ctx;
}
