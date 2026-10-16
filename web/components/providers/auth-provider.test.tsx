import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/components/providers/auth-provider";
import { invalidateSession } from "@/lib/api/client";
import { PARENT_PERMISSIONS, mockApi, problem, user } from "@/tests/fixtures";

const ME = user("parent", PARENT_PERMISSIONS);
const TOKENS = { access_token: "acc_2", expires_in: 900, user: ME };
const ABSENT = problem(401, "UNAUTHENTICATED", "No cookie session.");
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
      <button onClick={() => void logout().catch(() => undefined)}>log out</button>
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
beforeEach(() => invalidateSession());
afterEach(() => vi.unstubAllGlobals());

describe("cookie auth provider", () => {
  it("asks the server for the HttpOnly session even with empty browser storage", async () => {
    const fetchMock = mockApi({ "/auth/browser/session": ABSENT });
    mount();
    expect(await screen.findByText("ready")).toBeInTheDocument();
    expect(screen.getByText("signed out")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: "same-origin" });
  });
  it("restores a new tab with no JS refresh credential", async () => {
    mockApi({ "/auth/browser/session": TOKENS });
    mount();
    expect(await screen.findByText("signed in as Demo parent")).toBeInTheDocument();
    expect(sessionStorage.getItem("sr.refresh")).toBeNull();
  });
  it("deduplicates StrictMode restores", async () => {
    const fetchMock = mockApi({ "/auth/browser/session": TOKENS });
    mount(true);
    await screen.findByText("signed in as Demo parent");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("removes obsolete credentials from both storage types", async () => {
    sessionStorage.setItem("sr.refresh", "old-tab-token");
    localStorage.setItem("sr.refresh", "unsafe-token");
    mockApi({ "/auth/browser/session": ABSENT });
    mount();
    await screen.findByText("ready");
    expect(sessionStorage.getItem("sr.refresh")).toBeNull();
    expect(localStorage.getItem("sr.refresh")).toBeNull();
  });
  it("login/logout never write access or refresh credentials to storage", async () => {
    const fetchMock = mockApi({
      "/auth/browser/session": ABSENT,
      "/auth/browser/login": TOKENS,
      "/auth/browser/logout": { signed_out: true },
    });
    mount();
    await screen.findByText("ready");
    await userEvent.click(screen.getByText("log in"));
    await screen.findByText("signed in as Demo parent");
    expect(JSON.stringify(Object.entries(sessionStorage))).not.toContain("acc_2");
    expect(JSON.stringify(Object.entries(localStorage))).not.toContain("acc_2");
    await userEvent.click(screen.getByText("log out"));
    await screen.findByText("signed out");
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/auth/browser/logout"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({});
  });
  it("does not pretend logout succeeded when the cookie could not be revoked", async () => {
    mockApi({
      "/auth/browser/session": ABSENT,
      "/auth/browser/login": TOKENS,
      "/auth/browser/logout": problem(429, "RATE_LIMITED", "Slow down"),
    });
    mount();
    await screen.findByText("ready");
    await userEvent.click(screen.getByText("log in"));
    await screen.findByText("signed in as Demo parent");
    await userEvent.click(screen.getByText("log out"));
    await waitFor(() => expect(screen.getByText("signed in as Demo parent")).toBeInTheDocument());
  });
  it("does not crash on temporary restore network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    mount();
    await screen.findByText("ready");
    expect(screen.getByText("signed out")).toBeInTheDocument();
  });
  it("refuses use outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow("useAuth must be used inside AuthProvider");
    spy.mockRestore();
  });
});
