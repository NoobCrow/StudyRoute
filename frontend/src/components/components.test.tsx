import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "../auth/AuthContext";
import { invalidateSession } from "../api/client";
import { useIdempotencyKey } from "../idempotency";
import { QUOTE, problem, mockApi } from "../test/fixtures";
import { Countdown } from "./Countdown";
import { QuoteTable } from "./QuoteTable";
import { ResetCard } from "./ResetCard";
import { SandboxBanner } from "./SandboxBanner";

afterEach(() => vi.unstubAllGlobals());

describe("QuoteTable", () => {
  it("ranks providers and shows the shortfall as a red warning", () => {
    render(<QuoteTable quote={QUOTE} selected="prov_b" />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Provider B");
    expect(rows[0]).toHaveTextContent("Lowest cost");
    expect(rows[1]).toHaveTextContent("Provider C");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Short by GBP 35.00");
    expect(alert).toHaveClass("danger");
  });

  it("shows only values formatted by the server (no client-side money maths)", () => {
    render(<QuoteTable quote={QUOTE} selected={null} />);
    expect(screen.getAllByText("BDT 1,625,300.00").length).toBeGreaterThan(0);
  });
});

describe("Countdown", () => {
  it("says the quote expired once the time has passed", () => {
    render(<Countdown expiresAt="2000-01-01T00:00:00Z" />);
    expect(screen.getByText("Quote expired")).toBeInTheDocument();
  });
});

describe("SandboxBanner", () => {
  it("always carries the sandbox sentence and the indicative disclaimer", () => {
    render(<SandboxBanner />);
    expect(screen.getByRole("region", { name: "Sandbox notice" })).toHaveTextContent("Sandbox - synthetic data - no real money moves");
    expect(screen.getByRole("region", { name: "Sandbox notice" })).toHaveTextContent("Confirm with your AD bank");
  });
});

describe("useIdempotencyKey", () => {
  it("keeps the key for a retry and changes it when the request changes", () => {
    const { result, rerender } = renderHook(({ f }) => useIdempotencyKey(f), { initialProps: { f: "a" } });
    const first = result.current;
    rerender({ f: "a" });
    expect(result.current).toBe(first);
    rerender({ f: "b" });
    expect(result.current).not.toBe(first);
  });
});

describe("sign out", () => {
  it("keeps the account when server logout fails", async () => {
    invalidateSession();
    mockApi({
      "/auth/browser/login": { access_token: "a", refresh_token: "r".repeat(20), expires_in: 900, expires_at: "x", user: { user_id: "u", role: "parent", permissions: [] } },
      "/auth/browser/logout": problem(429, "RATE_LIMITED", "Slow down."),
    });
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await act(async () => result.current.login("a@b.test", "pw"));
    expect(result.current.user).not.toBeNull();
    await act(async () => { await expect(result.current.logout()).rejects.toMatchObject({status: 429}); });
    expect(result.current.user).not.toBeNull();
  });
});

describe("ResetCard", () => {
  it("asks twice and sends nothing until the second click", async () => {
    const fetchMock = mockApi({ "/me/reset": { reset: true, deleted: { payments: 2, recipients: 1 } } });
    const done = vi.fn();
    render(<ResetCard onDone={done} />);
    await userEvent.click(screen.getByRole("button", { name: "Reset my data" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete my data" }));
    expect(await screen.findByText("Your data was deleted")).toBeInTheDocument();
    expect(screen.getByText(/2 payments, 1 recipients/)).toBeInTheDocument();
    expect(done).toHaveBeenCalledTimes(1);
  });

  it("lets the user back out", async () => {
    const fetchMock = mockApi({});
    render(<ResetCard onDone={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Reset my data" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.getByRole("button", { name: "Reset my data" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
