"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  get,
  getRefreshToken,
  onSessionExpired,
  post,
  setAccessToken,
  setRefreshToken,
} from "@/lib/api/client";
import type { LoginResponse, RefreshResponse, UserView } from "@/lib/api/types";

interface AuthState {
  user: UserView | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

let restoring: Promise<UserView | null> | null = null;

/**
 * Brings the session back from the refresh token. A refresh token works once, so the request is shared:
 * React may run the effect twice in development, and a second use of the same token would be refused.
 */
function restoreSession(): Promise<UserView | null> {
  if (restoring === null) {
    restoring = (async () => {
      const stored = getRefreshToken();
      if (!stored) return null;
      try {
        const tokens = await post<RefreshResponse>(
          "/auth/refresh",
          { refresh_token: stored },
          { auth: false },
        );
        setAccessToken(tokens.access_token);
        setRefreshToken(tokens.refresh_token);
        return await get<UserView>("/me");
      } catch {
        setAccessToken(null);
        setRefreshToken(null);
        return null;
      }
    })().finally(() => {
      restoring = null;
    });
  }
  return restoring;
}

/** Keeps the access token in memory and only the refresh token in sessionStorage (never a password). */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserView | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    onSessionExpired(() => setUser(null));
    let current = true;
    restoreSession()
      .then((restored) => current && setUser(restored))
      .finally(() => current && setReady(true));
    return () => {
      current = false;
      onSessionExpired(null);
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await post<LoginResponse>("/auth/login", { email, password }, { auth: false });
    setAccessToken(result.access_token);
    setRefreshToken(result.refresh_token);
    setUser(result.user);
  }, []);

  const logout = useCallback(async () => {
    const token = getRefreshToken();
    try {
      if (token) await post("/auth/logout", { refresh_token: token }, { auth: false });
    } catch {
      /* the server could not revoke the token (offline, rate limited): sign out locally anyway */
    } finally {
      setAccessToken(null);
      setRefreshToken(null);
      setUser(null);
    }
  }, []);

  const reloadUser = useCallback(async () => setUser(await get<UserView>("/me")), []);

  const value = useMemo(
    () => ({ user, ready, login, logout, reloadUser }),
    [user, ready, login, logout, reloadUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
