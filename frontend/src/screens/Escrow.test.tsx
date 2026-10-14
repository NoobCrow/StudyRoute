import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/AuthContext";
import {
  CHAIN_STATUS, PARENT_PERMISSIONS, RECIPIENT, corridor, escrowView, mockApi, tranche, user, verdict,
} from "../test/fixtures";
import { EscrowScreen } from "./Escrow";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

const PARENT = [...PARENT_PERMISSIONS, "escrow:read", "escrow:write", "chain:read"];
const STUDENT = ["escrow:read", "chain:read"];
const ADMIN = ["escrow:read", "escrow:freeze", "chain:read", "chain:anchor", "audit:verify", "sandbox:control"];
const CORRIDORS = { items: [corridor({ account_scheme: "IBAN" })], providers: [] };

function signIn(role: "parent" | "student" | "admin", permissions: string[]) {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions), ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
}

function api(escrows: unknown[], extra: Record<string, unknown> = {}) {
  return mockApi({
    "/escrows": { items: escrows },
    "/chain/status": CHAIN_STATUS,
    "/chain/anchors": { items: [] },
    "/recipients": { items: [RECIPIENT] },
    "/corridors": CORRIDORS,
    "/health": { mode: "sandbox", demo: { mfa_code: "246810" } },
    ...extra,
  });
}

function show() {
  return render(<MemoryRouter><EscrowScreen /></MemoryRouter>);
}

beforeEach(() => signIn("parent", PARENT));
afterEach(() => vi.unstubAllGlobals());

describe("smart escrow screen", () => {
  it("says up front that the chain is simulated and nothing is money", async () => {
    api([]);
    show();
    expect(await screen.findByText("A simulated chain")).toBeInTheDocument();
    expect(screen.getByText(/no real\s+tokens, nothing is money/)).toBeInTheDocument();
    expect(await screen.findByText("No escrows yet.")).toBeInTheDocument();
  });

  it("shows the schedule, the state of every tranche and the proof on the chain", async () => {
    api([escrowView({ tranches: [tranche(0, { state: "RELEASED", release_on: "2026-10-28" }), tranche(1, { due: true }), tranche(2)] })]);
    show();
    const card = await screen.findByRole("article", { name: /Escrow Fall living costs/ });
    expect(within(card).getByText("Living costs: GBP 900.00")).toBeInTheDocument();
    expect(within(card).getByText("Active on the chain")).toBeInTheDocument();
    expect(within(card).getByText("Paid")).toBeInTheDocument();
    expect(within(card).getByText("Due now")).toBeInTheDocument();
    expect(within(card).getAllByText("Locked")).toHaveLength(2);
    await userEvent.click(within(card).getByText(/On-chain proof/));
    expect(within(card).getByText(/escrow contract$/)).toBeInTheDocument();
    expect(within(card).getByText("token:GBP.mint")).toBeInTheDocument();
    expect(within(card).getByText(/no name, account number or BIC ever is/)).toBeInTheDocument();
  });

  it("plans an escrow in the recipient's currency and decimals, with an idempotency key", async () => {
    const japan = corridor({ country: "JP", name: "Japan", currency: "JPY", account_scheme: "ACCOUNT", exponent: 0, featured: false, sample_amount: "2000000" });
    const planned = escrowView({ status: "PENDING_CONFIRMATION", chain_status: null, chain: null });
    const fetchMock = api([], {
      "/escrows": (init?: RequestInit) =>
        init?.method === "POST"
          ? new Response(JSON.stringify(planned), { status: 201, headers: { "Content-Type": "application/json" } })
          : { items: [] },
      "/corridors": { items: [corridor(), japan], providers: [] },
      "/recipients": { items: [{ ...RECIPIENT, country: "JP", label: "Tokyo University GB** 1234" }] },
    });
    show();
    await userEvent.selectOptions(await screen.findByLabelText("What for"), "TUITION");
    expect((screen.getByLabelText(/Total to lock/) as HTMLInputElement).value).toBe("2000000");
    expect(screen.getByLabelText(/Total to lock \(JPY\)/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Reference"), "INV-1");
    await userEvent.click(screen.getByRole("button", { name: "Plan escrow" }));
    const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/escrows") && init?.method === "POST");
    expect(call).toBeDefined();
    const init = call?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    const body = JSON.parse(String(init.body)) as { total: { amount_minor: number; currency: string }; tranches: number; cadence: string };
    expect(body.total).toEqual({ amount_minor: 2000000, currency: "JPY" });
    expect(body.tranches).toBe(1);
    expect(body.cadence).toBe("ONCE");
  });

  it("switching to living costs suggests three monthly payments", async () => {
    api([]);
    show();
    await userEvent.selectOptions(await screen.findByLabelText("What for"), "LIVING");
    expect((screen.getByLabelText("Number of payments") as HTMLInputElement).value).toBe("3");
    expect((screen.getByLabelText(/Total to lock/) as HTMLInputElement).value).toBe("3000");
    expect(screen.getByText("First payment on")).toBeInTheDocument();
  });

  it("locks funds only after MFA for that exact escrow, then sends the proof with a key", async () => {
    const pending = escrowView({ status: "PENDING_CONFIRMATION", chain_status: null, chain: null, transactions: [] });
    const fetchMock = api([pending], {
      "/auth/mfa/verify": { mfa_proof: "proof-123" },
      "/escrows/esc_1/confirm": escrowView(),
    });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Lock funds with MFA" }));
    expect(screen.getByRole("heading", { name: "Lock these funds in the escrow" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("MFA code"), "246810");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/escrows/esc_1/confirm"))).toBe(true));
    const mfa = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/auth/mfa/verify"));
    expect(JSON.parse(String((mfa?.[1] as RequestInit).body))).toMatchObject({ scope: "confirm_escrow", subject_id: "esc_1" });
    const confirm = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/escrows/esc_1/confirm"));
    const headers = (confirm?.[1] as RequestInit).headers as Record<string, string>;
    expect(headers["X-MFA-Proof"]).toBe("proof-123");
    expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("will not offer to lock funds while KYC is unverified", async () => {
    api([escrowView({ status: "PENDING_CONFIRMATION", chain_status: null, chain: null, blockers: [{ code: "KYC_NOT_VERIFIED", message: "KYC must be verified before funds can be locked (simulated)." }] })]);
    show();
    expect(await screen.findByRole("button", { name: "Lock funds with MFA" })).toBeDisabled();
    expect(screen.getByText("Not ready to lock funds")).toBeInTheDocument();
  });

  it("paying a tranche early and cancelling each ask for MFA with their own scope", async () => {
    api([escrowView()], { "/auth/mfa/verify": { mfa_proof: "p" } });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Pay tranche 2 now" }));
    expect(screen.getByRole("heading", { name: "Pay this tranche now" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel what is not yet due" }));
    expect(screen.getByRole("heading", { name: "Cancel the tranches that are not yet due" })).toBeInTheDocument();
  });

  it("a frozen escrow explains itself and offers no way to move money", async () => {
    api([escrowView({ chain_status: "FROZEN" })]);
    show();
    expect(await screen.findByText("Frozen by the bank's reviewer")).toBeInTheDocument();
    expect(screen.getByText(/Nobody can pay, return or cancel until it is unfrozen/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pay tranche/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel what is not yet due" })).toBeNull();
  });

  it("a student can look but has no plan form and no buttons that move money", async () => {
    signIn("student", STUDENT);
    api([escrowView()]);
    show();
    expect(await screen.findByRole("article", { name: /Escrow Fall living costs/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Plan an escrow" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Pay tranche/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Cancel what is not yet due/ })).toBeNull();
    expect(screen.queryByRole("form", { name: /Reviewer control/ })).toBeNull();
  });

  it("the reviewer can freeze with a written reason but cannot pay or plan", async () => {
    signIn("admin", ADMIN);
    const fetchMock = api([escrowView()], { "/escrows/esc_1/freeze": escrowView({ chain_status: "FROZEN" }) });
    show();
    const form = await screen.findByRole("form", { name: /Reviewer control/ });
    expect(screen.queryByRole("heading", { name: "Plan an escrow" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Pay tranche/ })).toBeNull();
    const freeze = within(form).getByRole("button", { name: "Freeze this escrow" });
    expect(freeze).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Reason to freeze"), "Sanctions screening hit");
    await userEvent.click(freeze);
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/escrows/esc_1/freeze"))).toBe(true));
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/freeze"));
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ reason: "Sanctions screening hit" });
    expect(screen.getByRole("heading", { name: "Sandbox clock" })).toBeInTheDocument();
  });

  it("the reviewer's verdict says plainly when the database does not match the chain", async () => {
    signIn("admin", ADMIN);
    api([], {
      "/chain/anchors": { items: [{ index: 0, seq: 12, head: "9".repeat(64), time: "2026-10-14T05:02:00Z" }] },
      "/chain/verify": verdict({
        status: "FAIL", failed: [0],
        anchors: [{ index: 0, seq: 12, head: "9".repeat(64), time: "2026-10-14T05:02:00Z", database_hash: "7".repeat(64), state: "MISMATCH" }],
      }),
    });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Verify against the chain" }));
    expect(await screen.findByText("Does NOT match the chain")).toBeInTheDocument();
    expect(screen.getByText(/does not match/)).toBeInTheDocument();
    expect(screen.getByText("passes")).toBeInTheDocument();
  });

  it("a parent can read the anchors but has no anchor or verify buttons", async () => {
    api([], { "/chain/anchors": { items: [{ index: 0, seq: 12, head: "9".repeat(64), time: "2026-10-14T05:02:00Z" }] } });
    show();
    expect(await screen.findByText("Audit event")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anchor the audit log now" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify against the chain" })).toBeNull();
  });

  it("shows the contracts and whether the log is intact", async () => {
    api([]);
    show();
    expect(await screen.findByText("TuitionEscrow")).toBeInTheDocument();
    expect(screen.getByText("Log intact")).toBeInTheDocument();
  });
});
