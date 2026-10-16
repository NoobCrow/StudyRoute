import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, newKey, post, setAccessToken, clearLegacyAuthStorage } from "./client";

function respond(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  const base = { "Content-Type": "application/json", ...headers };
  return new Response(JSON.stringify(body), { status, headers: base });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  setAccessToken("access-1");
  clearLegacyAuthStorage();
});
afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("sends the bearer token, the idempotency key and the MFA proof", async () => {
    fetchMock.mockResolvedValueOnce(respond(200, { ok: true }));
    const body = { confirm_summary_hash: "sha256:x" };
    await post("/payments/pay_1/approve", body, { idempotencyKey: "key-1", mfaProof: "mfa_1" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    const headers = init?.headers as Record<string, string>;
    expect(url).toBe("/api/v1/payments/pay_1/approve");
    expect(headers.Authorization).toBe("Bearer access-1");
    expect(headers["Idempotency-Key"]).toBe("key-1");
    expect(headers["X-MFA-Proof"]).toBe("mfa_1");
    expect(init?.credentials).toBe("same-origin");
  });

  it("turns RFC 7807 problems into ApiError with the code and request id", async () => {
    fetchMock.mockResolvedValueOnce(
      respond(409, {
        type: "x",
        title: "Quote expired",
        status: 409,
        code: "QUOTE_EXPIRED",
        detail: "Request a new quote.",
        request_id: "req_1",
        limit: "DAILY_CAP",
      }),
    );
    const error = await api("GET", "/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "QUOTE_EXPIRED",
      requestId: "req_1",
      message: "Request a new quote.",
      extra: { limit: "DAILY_CAP" },
    });
  });

  it("reads Retry-After on 429", async () => {
    fetchMock.mockResolvedValueOnce(
      respond(429, { code: "RATE_LIMITED", detail: "slow" }, { "Retry-After": "12" }),
    );
    const error = (await api("GET", "/x").catch((e: unknown) => e)) as ApiError;
    expect(error.retryAfter).toBe(12);
  });

  it("refreshes once after a 401 and retries with the new token", async () => {
    fetchMock
      .mockResolvedValueOnce(respond(401, { code: "UNAUTHENTICATED", detail: "expired" }))
      .mockResolvedValueOnce(
        respond(200, { access_token: "access-2", refresh_token: "refresh-2", expires_in: 900 }),
      )
      .mockResolvedValueOnce(respond(200, { hello: "world" }));
    await expect(api("GET", "/me")).resolves.toEqual({ hello: "world" });
    const retry = fetchMock.mock.calls[2]?.[1]?.headers as Record<string, string>;
    expect(retry.Authorization).toBe("Bearer access-2");
    expect(sessionStorage.getItem("sr.refresh")).toBeNull();
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/auth/browser/session");
  });

  it("signs the user out when the refresh fails", async () => {
    fetchMock
      .mockResolvedValueOnce(respond(401, { code: "UNAUTHENTICATED", detail: "expired" }))
      .mockResolvedValueOnce(respond(401, { code: "UNAUTHENTICATED", detail: "bad refresh" }));
    await expect(api("GET", "/me")).rejects.toBeInstanceOf(ApiError);
    expect(sessionStorage.getItem("sr.refresh")).toBeNull();
  });

  it("creates UUID v4 idempotency keys even without crypto.randomUUID", () => {
    const pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    expect(newKey()).toMatch(pattern);
    const original = crypto.randomUUID;
    Object.defineProperty(crypto, "randomUUID", { value: undefined, configurable: true });
    try {
      expect(newKey()).toMatch(pattern);
    } finally {
      Object.defineProperty(crypto, "randomUUID", { value: original, configurable: true });
    }
  });
});

it("does not refresh or replace the server's invalid-MFA error", async () => {
  fetchMock.mockResolvedValueOnce(respond(401, {code:"MFA_INVALID",detail:"That code is not valid."}));
  await expect(post("/auth/mfa/verify",{code:"000000"})).rejects.toMatchObject({code:"MFA_INVALID"});
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("does not resurrect an old cookie restore after logout/account change", async () => {
  const { restoreBrowserSession, invalidateSession, onSessionRestored } = await import("./client");
  const restored=vi.fn();onSessionRestored(restored);
  let resolve!: (response: Response)=>void;
  fetchMock.mockImplementationOnce(()=>new Promise<Response>(r=>{resolve=r;}));
  const pending=restoreBrowserSession();
  invalidateSession();setAccessToken("new-account-access");
  resolve(respond(200,{access_token:"old-account-access",user:{user_id:"old"}}));
  expect(await pending).toBeNull();expect(restored).not.toHaveBeenCalled();onSessionRestored(null);
  fetchMock.mockResolvedValueOnce(respond(200,{ok:true}));await post("/probe");
  expect((fetchMock.mock.calls.at(-1)?.[1]?.headers as Record<string,string>).Authorization).toBe("Bearer new-account-access");
});

it("does not clear a new access token when an older retry finishes", async () => {
  const { invalidateSession } = await import("./client");
  let resolve!: (response: Response)=>void;
  fetchMock.mockResolvedValueOnce(respond(401,{code:"UNAUTHENTICATED"}));
  fetchMock.mockImplementationOnce(()=>new Promise<Response>(r=>{resolve=r;}));
  const pending=api("GET","/old");const rejected=expect(pending).rejects.toBeInstanceOf(ApiError);
  await vi.waitFor(()=>expect(fetchMock).toHaveBeenCalledTimes(2));
  invalidateSession();setAccessToken("new-account-access");
  resolve(respond(200,{access_token:"old-account-access",user:{user_id:"old"}}));await rejected;
  fetchMock.mockResolvedValueOnce(respond(200,{ok:true}));await post("/probe");
  expect((fetchMock.mock.calls.at(-1)?.[1]?.headers as Record<string,string>).Authorization).toBe("Bearer new-account-access");
});
