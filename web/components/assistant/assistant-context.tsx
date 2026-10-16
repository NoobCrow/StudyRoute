"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useCurrentChatScope } from "@/hooks/use-chat-scope";
import { post } from "@/lib/api/client";
import type { ChatResponse, CloudConnection, ConnectionResult, PendingTask } from "@/lib/api/types";

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
  connected: { provider: string; model: string } | null;
  connectionResult: ConnectionResult | null;
  connecting: boolean;
  connect: (connection: CloudConnection) => Promise<boolean>;
  disconnect: () => void;
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
  const credentials = useRef<CloudConnection | null>(null);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const locked = useRef(false);
  const [connected, setConnected] = useState<{ provider: string; model: string } | null>(null);
  const [connectionResult, setConnectionResult] = useState<ConnectionResult | null>(null);
  const [connecting, setConnecting] = useState(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      credentials.current = null;
      controller.current?.abort();
    };
  }, []);

  const connect = useCallback(async (connection: CloudConnection) => {
    if (locked.current) return false;
    locked.current = true;
    setConnecting(true);
    setError(null);
    setConnectionResult(null);
    controller.current = new AbortController();
    try {
      const result = await post<ConnectionResult>("/assistant/connection/test", connection, {
        signal: controller.current.signal,
      });
      if (!mounted.current) return false;
      setConnectionResult(result);
      if (!result.ok) return false;
      credentials.current = connection;
      setMode(null);
      setConnected({ provider: connection.provider, model: result.model ?? "configured model" });
      return true;
    } catch (e) {
      if (mounted.current) setError(e as Error);
      return false;
    } finally {
      locked.current = false;
      if (mounted.current) setConnecting(false);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (locked.current) return;
    credentials.current = null;
    setConnected(null);
    setConnectionResult(null);
    setMode(null);
  }, []);

  const ask = useCallback(
    async (message: string) => {
      const clean = message.trim();
      if (!clean || locked.current) return;
      locked.current = true;
      controller.current = new AbortController();
      setError(null);
      setBusy(true);
      setTurns((t) => [...t, { id: ++counter.current, role: "me", text: clean }]);
      try {
        const context = {
          quote_id: scope.quoteId ?? planQuote,
          payment_id: scope.paymentId ?? null,
          pending,
          conversation: turns.slice(-6).map((t) => ({
            role: t.role === "me" ? "user" : "assistant",
            text: t.text.slice(0, 2000),
          })),
          history: turns
            .filter((t) => t.role === "me")
            .slice(-6)
            .map((t) => t.text),
        };
        const reply = await post<ChatResponse>(
          "/assistant/chat",
          {
            message: clean,
            context,
            ...(credentials.current ? { connection: credentials.current } : {}),
          },
          { signal: controller.current.signal },
        );
        if (!mounted.current) return;
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
        if (mounted.current) setError(e as Error);
      } finally {
        locked.current = false;
        if (mounted.current) setBusy(false);
      }
    },
    [scope.quoteId, scope.paymentId, planQuote, pending, turns],
  );

  const value = useMemo(
    () => ({
      turns,
      busy,
      error,
      mode,
      ask,
      connected,
      connectionResult,
      connecting,
      connect,
      disconnect,
    }),
    [turns, busy, error, mode, ask, connected, connectionResult, connecting, connect, disconnect],
  );
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantState {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside AssistantProvider");
  return ctx;
}
