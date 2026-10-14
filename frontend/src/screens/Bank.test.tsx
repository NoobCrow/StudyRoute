import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import {
  BANK_NETWORK, BANK_PERMISSIONS, BANK_TOTALS, KYC, bankAccount, bankTransfer, beneficiary, mockApi,
  problem, user,
} from "../test/fixtures";
import { BankScreen } from "./Bank";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

function signIn(role: Role, permissions: string[]) {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions), ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
}

const ACCOUNTS = { items: [bankAccount()], totals: BANK_TOTALS };
const PEOPLE = {
  items: [
    beneficiary(),
    beneficiary({ id: "bacc_rel", holder: "Demo Relative (synthetic)", bank_code: "EXMPBDB1", bank_name: "Example Bank B (sandbox)", country: "BD", currency: "BDT", number: "SBX-B-0002" }),
  ],
};

function routes(extra: Record<string, unknown> = {}) {
  return {
    "/bank/network": BANK_NETWORK,
    "/bank/accounts": ACCOUNTS,
    "/bank/beneficiaries": PEOPLE,
    "/bank/transfers": { items: [] },
    "/kyc/status": KYC,
    "/health": { mode: "sandbox", demo: { password: "x", mfa_code: "246810", accounts: [], parent_id: "p" } },
    ...extra,
  };
}

beforeEach(() => signIn("parent", [...BANK_PERMISSIONS, "payments:read"]));
afterEach(() => vi.unstubAllGlobals());

const body = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body));
const header = (call: unknown[], name: string) => ((call[1] as RequestInit).headers as Record<string, string>)[name];

describe("bank network screen", () => {
  it("shows the accounts with balances and says everything is simulated", async () => {
    mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    expect(await screen.findByText("BDT 5,000,000.00")).toBeInTheDocument();
    expect(screen.getByText("Everything here is simulated")).toBeInTheDocument();
    expect(screen.getByText("All books balance")).toBeInTheDocument();
  });

  it("shows the household's money in every currency with an indicative BDT total", async () => {
    mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    expect(await screen.findByText("Your money in every currency")).toBeInTheDocument();
    expect(screen.getByText("BDT 15,128,000.00")).toBeInTheDocument();
    expect(screen.getByText("GBP 800.00")).toBeInTheDocument();
    expect(screen.getByText(/Not a live FX feed/)).toBeInTheDocument();
  });

  it("puts the identity check on the page for a parent who is not verified yet", async () => {
    mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    expect(await screen.findByText("Identity check (simulated)")).toBeInTheDocument();
  });

  it("leaves the identity check out once the parent is verified", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { ...user("parent", [...BANK_PERMISSIONS, "payments:read"]), kyc_status: "VERIFIED" },
      ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
    });
    mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByText("Your money in every currency");
    expect(screen.queryByText("Identity check (simulated)")).toBeNull();
  });

  it("offers only sensible destinations and plans an international transfer with an Idempotency-Key", async () => {
    const created = bankTransfer();
    const fetchMock = mockApi(routes({ "/bank/transfers": (init: RequestInit | undefined) => (init?.method === "POST" ? created : { items: [] }) }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByLabelText("To account");
    await userEvent.selectOptions(screen.getByLabelText("To account"), "bacc_uni");
    await userEvent.type(screen.getByLabelText(/Amount the beneficiary receives \(GBP\)/), "10,000.00");
    await userEvent.selectOptions(screen.getByLabelText("Who pays the fees"), "OUR");
    await userEvent.click(screen.getByRole("button", { name: "Plan transfer" }));
    expect(await screen.findByText("Waiting for your confirmation")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST");
    expect(post).toBeDefined();
    expect(body(post as unknown[])).toEqual({
      source: "bacc_parent_a", destination: "bacc_uni",
      amount: { amount_minor: 1_000_000, currency: "GBP" }, reference: "Sandbox transfer", charge_code: "OUR",
    });
    expect(header(post as unknown[], "Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByText("BDT 1,630,000.00", { selector: "dd" })).toBeInTheDocument();
  });

  it("shows a rail choice, not a charge code, for a national transfer", async () => {
    mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByLabelText("To account");
    await userEvent.selectOptions(screen.getByLabelText("To account"), "bacc_rel");
    expect(screen.getByLabelText("Way of sending")).toBeInTheDocument();
    expect(screen.queryByLabelText("Who pays the fees")).toBeNull();
  });

  it("rejects an amount with too many decimals before calling the server", async () => {
    const fetchMock = mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByLabelText("To account");
    await userEvent.selectOptions(screen.getByLabelText("To account"), "bacc_rel");
    await userEvent.type(screen.getByLabelText(/Amount/), "10.555");
    await userEvent.click(screen.getByRole("button", { name: "Plan transfer" }));
    expect(await screen.findByText(/at most 2 decimal places/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")).toBe(false);
  });

  it("confirms with an MFA proof for that transfer and sends it in X-MFA-Proof", async () => {
    const pending = bankTransfer();
    const fetchMock = mockApi(routes({
      "/bank/transfers": { items: [pending] },
      "/bank/transfers/btr_1": pending,
      "/auth/mfa/verify": { mfa_proof: "proof_abc" },
      "/bank/transfers/btr_1/confirm": bankTransfer({ status: "ACCEPTED" }),
    }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: /Open transfer to University/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Confirm with MFA" }));
    await userEvent.type(screen.getByLabelText("MFA code"), "246810");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    const verify = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/auth/mfa/verify"));
    expect(body(verify as unknown[])).toEqual({ code: "246810", scope: "confirm_bank_transfer", subject_id: "btr_1" });
    const confirm = await vi.waitFor(() => {
      const found = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/btr_1/confirm"));
      expect(found).toBeDefined();
      return found as unknown[];
    });
    expect(header(confirm, "X-MFA-Proof")).toBe("proof_abc");
    expect(header(confirm, "Idempotency-Key")).toBeTruthy();
  });

  it("disables confirmation and explains why while a blocker exists", async () => {
    const blocked = bankTransfer({ blockers: [{ code: "KYC_NOT_VERIFIED", message: "KYC is not verified (simulated)." }] });
    mockApi(routes({ "/bank/transfers": { items: [blocked] }, "/bank/transfers/btr_1": blocked }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: /Open transfer to University/ }));
    expect(await screen.findByText("KYC is not verified (simulated).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm with MFA" })).toBeDisabled();
  });

  it("shows the hops, the messages and the double-entry ledger of a settled transfer", async () => {
    const settled = bankTransfer({
      status: "SETTLED",
      steps: bankTransfer().steps.map((s) => ({ ...s, done: true })),
      events: [{
        at: "2026-10-14T09:31:00Z", stage: "ORIGINATING_BANK", bank_code: "EXMPBDA1", bank_name: "Example Bank A (sandbox)",
        event: "step_done", note: "Originating bank sells currency and sends MT103",
        message: { type: "MT103", fields: [{ tag: ":71A:", name: "Details of charges", value: "OUR" }] },
      }],
      journals: [{
        id: "jrn_1", kind: "STEP", stage: "ORIGINATING_BANK", memo: "Sell foreign currency", posted_at: "2026-10-14T09:31:00Z",
        lines: [{ side: "DEBIT", bank: "Example Bank A (sandbox)", account: "IN_FLIGHT", amount: { amount_minor: 1, currency: "BDT", formatted: "BDT 0.01" } }],
      }],
    });
    mockApi(routes({ "/bank/transfers": { items: [settled] }, "/bank/transfers/btr_1": settled }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: /Open transfer to University/ }));
    const detail = await screen.findByRole("article");
    expect(within(detail).getAllByText("Done")).toHaveLength(3);
    expect(within(detail).getByText("Settled")).toBeInTheDocument();
    expect(within(detail).getByText("Messages and history (1)")).toBeInTheDocument();
    expect(within(detail).getByText(/Ledger entries, double entry/)).toBeInTheDocument();
    expect(within(detail).queryByRole("button", { name: "Confirm with MFA" })).toBeNull();
  });

  it("explains a returned transfer", async () => {
    const returned = bankTransfer({ status: "RETURNED", failure_reason: "The beneficiary bank rejected the payment (simulated)." });
    mockApi(routes({ "/bank/transfers": { items: [returned] }, "/bank/transfers/btr_1": returned }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: /Open transfer to University/ }));
    expect(await screen.findByText("The beneficiary bank rejected the payment (simulated).")).toBeInTheDocument();
    expect(screen.getAllByText("Returned in full").length).toBeGreaterThan(0);
    expect(screen.getByText("These were the planned figures. Nothing was charged.")).toBeInTheDocument();
  });

  it("shows a server refusal in plain words", async () => {
    mockApi(routes({ "/bank/transfers": (init: RequestInit | undefined) => (init?.method === "POST" ? problem(422, "SANCTIONS_HIT", "The beneficiary matched mock sanctions screening (simulated).") : { items: [] }) }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByLabelText("To account");
    await userEvent.selectOptions(screen.getByLabelText("To account"), "bacc_uni");
    await userEvent.type(screen.getByLabelText(/Amount/), "100");
    await userEvent.click(screen.getByRole("button", { name: "Plan transfer" }));
    expect(await screen.findByText(/matched mock sanctions screening/)).toBeInTheDocument();
  });
});

describe("roles", () => {
  it("gives a student the accounts but no way to plan a transfer", async () => {
    signIn("student", ["bank:read"]);
    mockApi(routes());
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByText("BDT 5,000,000.00");
    expect(screen.queryByText("Plan a transfer")).toBeNull();
  });

  it("lets the reviewer run the next hop or make an in-flight transfer fail", async () => {
    signIn("admin", ["bank:read", "sandbox:control"]);
    const flying = bankTransfer({ status: "IN_TRANSIT" });
    const fetchMock = mockApi(routes({
      "/bank/transfers": { items: [flying] },
      "/bank/transfers/btr_1": flying,
      "/bank/transfers/btr_1/sandbox-step": bankTransfer({ status: "RETURNED" }),
    }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: /Open transfer to University/ }));
    expect(screen.queryByText("Plan a transfer")).toBeNull();
    await userEvent.click(await screen.findByRole("button", { name: "Make it fail" }));
    const step = await vi.waitFor(() => {
      const found = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/sandbox-step"));
      expect(found).toBeDefined();
      return found as unknown[];
    });
    expect(body(step)).toEqual({ outcome: "fail" });
  });

  it("shows no household total to the reviewer", async () => {
    signIn("admin", ["bank:read", "sandbox:control"]);
    mockApi(routes({ "/bank/accounts": { items: [bankAccount()], totals: null } }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await screen.findByText("BDT 5,000,000.00");
    expect(screen.queryByText("Your money in every currency")).toBeNull();
  });

  it("tells the operator to run the seed when the network is missing", async () => {
    mockApi(routes({ "/bank/network": { ready: false, simulated: true } }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    expect(await screen.findByText("The bank network is not set up")).toBeInTheDocument();
    expect(screen.queryByText("Accounts")).toBeNull();
  });

  it("flags a ledger mismatch loudly", async () => {
    mockApi(routes({ "/bank/network": { ...BANK_NETWORK, all_ok: false } }));
    render(<MemoryRouter><BankScreen /></MemoryRouter>);
    expect(await screen.findByText("Mismatch found")).toBeInTheDocument();
  });
});
