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

import { useCurrentChatScope } from "../chatContext";
import { del, get, post, put } from "../api/client";
import type {
  ChatResponse,
  CloudConnection,
  ConnectionResult,
  SavedConnection,
  PendingTask,
} from "../api/types";

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
  connected: { provider: string; model: string; verified?: boolean } | null;
  connectionResult: ConnectionResult | null;
  connecting: boolean;
  connect: (connection: CloudConnection) => Promise<boolean>;
  disconnect: () => Promise<void>;
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
  const metadataRevision = useRef(0);
  const metadataRequest = useRef<AbortController | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const locked = useRef(false);
  const [connected, setConnected] = useState<{
    provider: string;
    model: string;
    verified?: boolean;
  } | null>(null);
  const [connectionResult, setConnectionResult] =
    useState<ConnectionResult | null>(null);
  const [connecting, setConnecting] = useState(false);
  // Only non-secret metadata returns to the browser. Chat resolves the saved key server-side.
  const refreshConnection = useCallback(async () => {
    if (locked.current) return;
    const revision = ++metadataRevision.current;
    metadataRequest.current?.abort();
    const request = new AbortController();
    metadataRequest.current = request;
    try {
      const result = await get<SavedConnection>("/assistant/connection", {
        signal: request.signal,
      });
      if (
        request.signal.aborted ||
        !mounted.current ||
        revision !== metadataRevision.current
      )
        return;
      setConnected(
        result.saved && result.provider
          ? {
              provider: result.provider,
              model: result.model ?? "configured model",
              verified: result.verified,
            }
          : null,
      );
    } catch (e) {
      if (
        !request.signal.aborted &&
        mounted.current &&
        revision === metadataRevision.current
      )
        setError(e as Error);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    queueMicrotask(() => {
      if (active) void refreshConnection();
    });
    const refresh = () => {
      if (document.visibilityState !== "hidden") void refreshConnection();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel("studyroute-ai-settings");
      channel.current.onmessage = (event: MessageEvent) => {
        if (event.data === "connection-changed") refresh();
      };
    }
    return () => {
      active = false;
      mounted.current = false;
      metadataRequest.current?.abort();
      controller.current?.abort();
      channel.current?.close();
      channel.current = null;
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [refreshConnection]);

  const connect = useCallback(async (connection: CloudConnection) => {
    if (locked.current) return false;
    locked.current = true;
    ++metadataRevision.current;
    metadataRequest.current?.abort();
    setConnecting(true);
    setError(null);
    setConnectionResult(null);
    controller.current = new AbortController();
    try {
      const result = await put<ConnectionResult>(
        "/assistant/connection",
        {
          ...connection,
          storage_consent: true,
        },
        { signal: controller.current.signal },
      );
      if (!mounted.current) return false;
      setConnectionResult(result);
      if (!result.ok || !result.saved) return false;
      setMode(null);
      setConnected({
        provider: connection.provider,
        model: result.model ?? "configured model",
        verified: result.verified,
      });
      channel.current?.postMessage("connection-changed");
      return true;
    } catch (e) {
      if (mounted.current) setError(e as Error);
      return false;
    } finally {
      locked.current = false;
      if (mounted.current) setConnecting(false);
    }
  }, []);

  const disconnect = useCallback(async () => {
    if (locked.current) return;
    locked.current = true;
    ++metadataRevision.current;
    metadataRequest.current?.abort();
    setConnecting(true);
    setError(null);
    controller.current = new AbortController();
    try {
      await del("/assistant/connection", { signal: controller.current.signal });
      if (!mounted.current) return;
      setConnected(null);
      setConnectionResult(null);
      setMode(null);
      channel.current?.postMessage("connection-changed");
    } catch (e) {
      if (mounted.current) setError(e as Error);
    } finally {
      locked.current = false;
      if (mounted.current) setConnecting(false);
    }
  }, []);

  const ask = useCallback(
    async (message: string) => {
      const clean = message.trim();
      if (!clean || locked.current) return;
      locked.current = true;
      controller.current = new AbortController();
      setError(null);
      setBusy(true);
      setTurns((t) => [
        ...t,
        { id: ++counter.current, role: "me", text: clean },
      ]);
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
          },
          { signal: controller.current.signal },
        );
        if (!mounted.current) return;
        setMode(reply);
        if (
          reply.task?.kind === "payment_plan" &&
          reply.task.status === "ready"
        )
          setPlanQuote(reply.task.quote.quote_id);
        const task = reply.task;
        const waiting =
          task &&
          (task.status === "needs_input" ||
            task.status === "needs_confirmation");
        setPending(
          waiting
            ? ({
                kind: task.kind,
                ...(task as { collected?: object }).collected,
              } as PendingTask)
            : null,
        );
        setTurns((t) => [
          ...t,
          { id: ++counter.current, role: "bot", text: reply.reply, reply },
        ]);
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
    [
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
    ],
  );
  return (
    <AssistantContext.Provider value={value}>
      {children}
    </AssistantContext.Provider>
  );
}

export function useAssistant(): AssistantState {
  const ctx = useContext(AssistantContext);
  if (!ctx)
    throw new Error("useAssistant must be used inside AssistantProvider");
  return ctx;
}
