import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/providers/auth-provider";
import { getRefreshToken, setAccessToken, setRefreshToken } from "@/lib/api/client";
import { PARENT_PERMISSIONS, mockApi, problem, user } from "@/tests/fixtures";

const ME = user("parent", PARENT_PERMISSIONS);
const TOKENS = {
  access_token: "acc_2",
  refresh_token: "ref_2",
  token_type: "bearer",
  expires_in: 900,
};

function Probe() {
  const { user: who, ready, login, logout } = useAuth();
  return (
    <div>
      <p>{ready ? "ready" : "loading"}</p>
      <p>{who ? `signed in as ${who.display_name}` : "signed out"}</p>
      <button
        onClick={() => void login("parent@demo.studyroute.test", "pw").catch(() => undefined)}
      >
        log in
      </button>
      <button onClick={() => void logout()}>log out</button>
    </div>
  );
}

function mount(strict = false) {
  const tree = (
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

beforeEach(() => {
  setAccessToken(null);
  setRefreshToken(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("auth provider", () => {
  it("is signed out and ready when there is no refresh token", async () => {
    const fetchMock = mockApi({});
    mount();
    expect(await screen.findByText("ready")).toBeInTheDocument();
    expect(screen.getByText("signed out")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("brings the session back from the refresh token", async () => {
    setRefreshToken("ref_1");
    mockApi({ "/auth/refresh": TOKENS, "/me": ME });
    mount();
    expect(await screen.findByText("signed in as Demo parent")).toBeInTheDocument();
    expect(getRefreshToken()).toBe("ref_2");
  });

  it("uses a refresh token only once even when React runs the effect twice", async () => {
    setRefreshToken("ref_1");
    const fetchMock = mockApi({ "/auth/refresh": TOKENS, "/me": ME });
    mount(true);
    expect(await screen.findByText("signed in as Demo parent")).toBeInTheDocument();
    const refreshes = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"));
    expect(refreshes).toHaveLength(1);
  });

  it("forgets a refresh token the server no longer accepts", async () => {
    setRefreshToken("stale");
    mockApi({ "/auth/refresh": problem(401, "TOKEN_INVALID", "Expired.") });
    mount();
    expect(await screen.findByText("signed out")).toBeInTheDocument();
    expect(getRefreshToken()).toBeNull();
  });

  it("signs in, keeps only the refresh token in session storage, and signs out", async () => {
    const fetchMock = mockApi({
      "/auth/login": { ...TOKENS, user: ME },
      "/auth/logout": { ok: true },
    });
    mount();
    await screen.findByText("ready");
    await userEvent.click(screen.getByRole("button", { name: "log in" }));
    expect(await screen.findByText("signed in as Demo parent")).toBeInTheDocument();
    expect(getRefreshToken()).toBe("ref_2");
    expect(JSON.stringify(Object.entries(sessionStorage))).not.toContain("acc_2");
    expect(JSON.stringify(Object.entries(sessionStorage))).not.toContain("pw");

    await userEvent.click(screen.getByRole("button", { name: "log out" }));
    expect(await screen.findByText("signed out")).toBeInTheDocument();
    expect(getRefreshToken()).toBeNull();
    const logout = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/auth/logout"));
    expect(JSON.parse(String((logout?.[1] as RequestInit).body))).toEqual({
      refresh_token: "ref_2",
    });
  });

  it("signs out locally even when the server cannot revoke the token (rate limited)", async () => {
    mockApi({
      "/auth/login": { ...TOKENS, user: ME },
      "/auth/logout": problem(429, "RATE_LIMITED", "Too many requests."),
    });
    mount();
    await screen.findByText("ready");
    await userEvent.click(screen.getByRole("button", { name: "log in" }));
    await screen.findByText("signed in as Demo parent");
    await userEvent.click(screen.getByRole("button", { name: "log out" }));
    await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
    expect(getRefreshToken()).toBeNull();
  });

  it("refuses to be used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow("useAuth must be used inside AuthProvider");
    spy.mockRestore();
  });
});
