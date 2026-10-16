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
import {
  clearLegacyAuthStorage,
  get,
  invalidateSession,
  onSessionExpired,
  onSessionRestored,
  post,
  restoreBrowserSession,
  setAccessToken,
} from "@/lib/api/client";
import type { BrowserSessionResponse, UserView } from "@/lib/api/types";

interface AuthState {
  user: UserView | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);
const CHANNEL = "studyroute-auth-v1";

/** HttpOnly cookie restores new tabs; access JWTs and provider keys stay in memory. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserView | null>(null);
  const [ready, setReady] = useState(false);
  const channel = useRef<BroadcastChannel | null>(null);
  const revision = useRef(0);
  const busy = useRef(false);
  const publish = useCallback(() => channel.current?.postMessage("auth-changed"), []);

  useEffect(() => {
    let current = true;
    clearLegacyAuthStorage();
    onSessionExpired(() => {
      if (current) setUser(null);
    });
    onSessionRestored((next) => {
      if (current && !busy.current) setUser(next);
    });
    const restore = async (reset = false) => {
      if (busy.current) return;
      const operation = ++revision.current;
      if (reset) {
        invalidateSession();
        setUser(null);
        setReady(false);
      }
      try {
        const result = await restoreBrowserSession();
        if (current && operation === revision.current) setUser(result?.user ?? null);
      } catch {
        // A network failure is not a server logout. Keep the cookie for a retry.
      } finally {
        if (current && operation === revision.current) setReady(true);
      }
    };
    void restore();
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel(CHANNEL);
      channel.current.onmessage = (event: MessageEvent<unknown>) => {
        if (event.data === "auth-changed") void restore(true);
      };
    }
    // Also revalidate when a suspended tab returns or BroadcastChannel is unavailable.
    const focus = () => {
      if (document.visibilityState === "visible") void restore();
    };
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", focus);
    return () => {
      current = false;
      revision.current += 1;
      onSessionExpired(null);
      onSessionRestored(null);
      channel.current?.close();
      channel.current = null;
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", focus);
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      busy.current = true;
      revision.current += 1;
      invalidateSession();
      try {
        const result = await post<BrowserSessionResponse>(
          "/auth/browser/login",
          { email, password },
          { auth: false },
        );
        setAccessToken(result.access_token);
        setUser(result.user);
        setReady(true);
        publish();
      } finally {
        busy.current = false;
      }
    },
    [publish],
  );

  const logout = useCallback(async () => {
    busy.current = true;
    revision.current += 1;
    invalidateSession();
    try {
      // Do not pretend to log out if the server could not revoke the HttpOnly cookie.
      await post("/auth/browser/logout", {}, { auth: false });
      setUser(null);
      clearLegacyAuthStorage();
      publish();
    } finally {
      busy.current = false;
    }
  }, [publish]);

  const reloadUser = useCallback(async () => setUser(await get<UserView>("/me")), []);
  const value = useMemo(
    () => ({ user, ready, login, logout, reloadUser }),
    [user, ready, login, logout, reloadUser],
  );
  return (
    <AuthContext.Provider value={value}>
      <AccountBoundary key={user?.user_id ?? "signed-out"}>{children}</AccountBoundary>
    </AuthContext.Provider>
  );
}

// Unmount account UI (including chat and its in-memory BYOK key) on account changes.
function AccountBoundary({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
