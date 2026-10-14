import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { PARENT_PERMISSIONS, mockApi, payment, user } from "../test/fixtures";
import { SandboxScreen } from "./Sandbox";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

const INFO = {
  sandbox: true, banner: "Sandbox - synthetic data - no real money moves",
  disclaimer: "Indicative guidance only. Confirm with your AD bank.", ai_mode: "template",
  simulated: [{ component: "Exchange rates", what: "Synthetic mid-market rates. Not a live FX feed." }],
  scenarios: [
    { token: "FAIL_TEST", where: "Recipient name", effect: "The simulated provider rejects the payment." },
    { token: "SLOW_TEST", where: "Recipient name", effect: "Settlement takes 30 seconds." },
  ],
  providers: [{ provider_id: "prov_b", name: "Provider B (synthetic)" }],
  timings: {
    quote_ttl_seconds: 300, mfa_proof_ttl_seconds: 300, kyc_review_seconds: 8,
    submit_delay_seconds: 3, settle_delay_seconds: 5, slow_settle_delay_seconds: 30,
  },
  limits: { per_transaction_usd_equivalent: 50000, daily_usd_equivalent: 100000, indicative: "Sandbox caps of our own choosing." },
  demo: { password: "Sandbox#2026", mfa_code: "246810" },
};
const IN_FLIGHT = { ...payment({ state: "SUBMITTED" }) };

function signIn(role: Role, permissions: string[]) {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions), ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
}

beforeEach(() => signIn("parent", PARENT_PERMISSIONS));
afterEach(() => vi.unstubAllGlobals());

describe("sandbox screen", () => {
  it("explains what is simulated and lists the test scenarios", async () => {
    mockApi({ "/sandbox": INFO });
    render(<MemoryRouter><SandboxScreen /></MemoryRouter>);
    expect(await screen.findByText("Not a live FX feed.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("FAIL_TEST")).toBeInTheDocument();
    expect(screen.getByText("Settlement takes 30 seconds.")).toBeInTheDocument();
    expect(screen.getByText("Template mode")).toBeInTheDocument();
    expect(screen.getByText("Provider B (synthetic)", { exact: false })).toBeInTheDocument();
  });

  it("gives a parent no control over the simulated provider", async () => {
    mockApi({ "/sandbox": INFO });
    render(<MemoryRouter><SandboxScreen /></MemoryRouter>);
    await screen.findByText("Test scenarios");
    expect(screen.queryByText("Simulated provider control")).toBeNull();
  });

  it("lets the reviewer settle or fail a payment that is in flight", async () => {
    signIn("admin", ["sandbox:control", "payments:read"]);
    const fetchMock = mockApi({
      "/sandbox": INFO,
      "/payments": { items: [IN_FLIGHT], next_cursor: null },
      "/sandbox/payments/pay_1/provider-event": { event: "payment.failed", note: "Sent on the next tick." },
    });
    render(<MemoryRouter><SandboxScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: "Fail now" }));
    expect(await screen.findByText(/payment.failed scheduled/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/provider-event"));
    expect(call?.[1]?.method).toBe("POST");
    expect(call?.[1]?.body).toBe(JSON.stringify({ outcome: "fail" }));
  });

  it("says so when nothing is in flight", async () => {
    signIn("admin", ["sandbox:control", "payments:read"]);
    mockApi({ "/sandbox": INFO, "/payments": { items: [], next_cursor: null } });
    render(<MemoryRouter><SandboxScreen /></MemoryRouter>);
    expect(await screen.findByText(/No payment is in flight right now/)).toBeInTheDocument();
  });
});
