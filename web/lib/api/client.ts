// Thin fetch wrapper: bearer token, refresh rotation, Idempotency-Key, RFC 7807 errors.
import type { Problem, RefreshResponse } from "./types";

const BASE = "/api/v1";
const REFRESH_KEY = "sr.refresh";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly title: string,
    detail: string,
    readonly requestId: string | null,
    readonly extra: Record<string, unknown> = {},
    readonly retryAfter: number | null = null,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

let accessToken: string | null = null;
let expiredHandler: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
export function onSessionExpired(handler: (() => void) | null): void {
  expiredHandler = handler;
}
export function getRefreshToken(): string | null {
  try {
    return sessionStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}
export function setRefreshToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(REFRESH_KEY, token);
    else sessionStorage.removeItem(REFRESH_KEY);
  } catch {
    /* storage can be blocked: the session simply will not survive a reload */
  }
}

/** A UUID v4 that also works on plain-http pages, where crypto.randomUUID is missing. */
export function newKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  const parts = [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ];
  return parts.join("-");
}

export interface CallOptions {
  idempotencyKey?: string;
  mfaProof?: string;
  headers?: Record<string, string>;
  auth?: boolean;
  signal?: AbortSignal;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export interface Reply<T> {
  data: T;
  status: number;
  headers: Headers;
}

async function send<T>(
  method: string,
  path: string,
  body: unknown,
  opts: CallOptions,
): Promise<Reply<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  if (opts.mfaProof) headers["X-MFA-Proof"] = opts.mfaProof;
  Object.assign(headers, opts.headers);
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: opts.signal,
    credentials: "omit",
  });
  const text = await response.text();
  const data: unknown = text ? safeJson(text) : null;
  if (response.ok) return { data: data as T, status: response.status, headers: response.headers };
  const problem = (data ?? {}) as Partial<Problem>;
  const retry = Number(response.headers.get("Retry-After"));
  const extra: Record<string, unknown> = { ...problem };
  for (const key of ["type", "title", "status", "code", "detail", "request_id"]) delete extra[key];
  throw new ApiError(
    response.status,
    problem.code ?? "HTTP_ERROR",
    problem.title ?? "Request failed",
    problem.detail ?? `The server answered ${response.status}.`,
    problem.request_id ?? response.headers.get("X-Request-Id"),
    extra,
    Number.isFinite(retry) && retry > 0 ? retry : null,
  );
}

let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const token = getRefreshToken();
  if (!token) return false;
  refreshing ??= (async () => {
    try {
      const { data: next } = await send<RefreshResponse>(
        "POST",
        "/auth/refresh",
        { refresh_token: token },
        { auth: false },
      );
      accessToken = next.access_token;
      setRefreshToken(next.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/** Like `api`, but also returns the status and headers (used to show Idempotent-Replay). */
export async function apiReply<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: CallOptions = {},
): Promise<Reply<T>> {
  try {
    return await send<T>(method, path, body, opts);
  } catch (error) {
    const expired = error instanceof ApiError && error.status === 401 && opts.auth !== false;
    if (!expired) throw error;
    if (await refreshTokens()) return send<T>(method, path, body, opts);
    setAccessToken(null);
    setRefreshToken(null);
    expiredHandler?.();
    throw error;
  }
}

export async function api<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: CallOptions = {},
): Promise<T> {
  return (await apiReply<T>(method, path, body, opts)).data;
}

export const get = <T>(path: string, opts?: CallOptions) => api<T>("GET", path, undefined, opts);
export const post = <T>(path: string, body?: unknown, opts?: CallOptions) =>
  api<T>("POST", path, body ?? {}, opts);
export const put = <T>(path: string, body: unknown, opts?: CallOptions) =>
  api<T>("PUT", path, body, opts);
export const patch = <T>(path: string, body: unknown, opts?: CallOptions) =>
  api<T>("PATCH", path, body, opts);
export const del = <T>(path: string, opts?: CallOptions) => api<T>("DELETE", path, undefined, opts);
