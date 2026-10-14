import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  getRefreshToken, get, onSessionExpired, post, setAccessToken, setRefreshToken,
} from "../api/client";
import type { LoginResponse, RefreshResponse, UserView } from "../api/types";

interface AuthState {
  user: UserView | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserView | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    onSessionExpired(() => setUser(null));
    const stored = getRefreshToken();
    if (!stored) {
      setReady(true);
      return () => onSessionExpired(null);
    }
    post<RefreshResponse>("/auth/refresh", { refresh_token: stored }, { auth: false })
      .then(async (tokens) => {
        setAccessToken(tokens.access_token);
        setRefreshToken(tokens.refresh_token);
        setUser(await get<UserView>("/me"));
      })
      .catch(() => {
        setAccessToken(null);
        setRefreshToken(null);
      })
      .finally(() => setReady(true));
    return () => onSessionExpired(null);
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

  const value = useMemo(() => ({ user, ready, login, logout, reloadUser }), [user, ready, login, logout, reloadUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
