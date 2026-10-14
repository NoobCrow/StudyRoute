// Automated accessibility checks (axe-core) on the main screens. jsdom cannot compute colours, so
// the contrast rule is checked separately in a real browser; everything else runs here.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ComplianceReport } from "./api/types";
import { useAuth } from "./auth/AuthContext";
import { ChatPanel } from "./components/ChatPanel";
import { SandboxBanner } from "./components/SandboxBanner";
import { BankScreen } from "./screens/Bank";
import { EscrowScreen } from "./screens/Escrow";
import { CompareScreen } from "./screens/Compare";
import { PaymentScreen } from "./screens/Payment";
import { RecipientsScreen } from "./screens/Recipients";
import { ReportScreen } from "./screens/Report";
import { SandboxScreen } from "./screens/Sandbox";
import {
  BANK_NETWORK, BANK_PERMISSIONS, BANK_TOTALS, KYC, PARENT_PERMISSIONS, PLAN_CARD, QUOTE, RECIPIENT, bankAccount,
  CHAIN_STATUS, bankTransfer, beneficiary, chatReply, corridor, escrowView, mockApi, payment, tranche, user, verdict,
} from "./test/fixtures";

vi.mock("./auth/AuthContext", () => ({ useAuth: vi.fn() }));

async function violations(container: HTMLElement): Promise<string[]> {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({
    user: user("parent", [...PARENT_PERMISSIONS, "audit:read", "planner:read"]), ready: true,
    login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
});
afterEach(() => vi.unstubAllGlobals());

const CORRIDORS = {
  items: [corridor()],
  providers: [],
};

describe("accessibility (axe)", () => {
  it("the harness really catches a defect, so a pass means something", async () => {
    const { container } = render(<div><button type="button" /><input /></div>);
    const found = (await violations(container)).map((v) => v.split(":")[0]);
    expect(found).toEqual(expect.arrayContaining(["button-name", "label"]));
  });

  it("the sandbox banner is a named landmark", async () => {
    const { container } = render(<SandboxBanner />);
    expect(screen.getByRole("region", { name: "Sandbox notice" })).toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
  });

  it("the compare screen with results", async () => {
    mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [RECIPIENT] }, "/quotes": QUOTE });
    const { container } = render(<MemoryRouter><CompareScreen /></MemoryRouter>);
    await screen.findByRole("option", { name: /United Kingdom/ });
    await userEvent.click(screen.getByRole("button", { name: "Get quotes" }));
    await screen.findByText("Lowest cost");
    expect(await violations(container)).toEqual([]);
  });

  it("the recipients screen", async () => {
    mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [RECIPIENT] }, "/health": { mode: "sandbox" } });
    const { container } = render(<MemoryRouter><RecipientsScreen /></MemoryRouter>);
    await screen.findByText("GB** **** 4821");
    expect(await violations(container)).toEqual([]);
  });

  it("a payment with its summary, blockers, preview and tracker", async () => {
    mockApi({
      "/payments/pay_1": payment({ readiness: { blockers: [{ code: "KYC_NOT_VERIFIED", message: "KYC is not verified (simulated)." }], can_request_approval: false, can_approve: false } }),
      "/payments/pay_1/tracker": { payment_id: "pay_1", uetr: null, state: "QUOTED", host_rail: "UK Faster Payments", simulated: true, timeline: [{ state: "QUOTED", at: "2026-10-14T09:31:00Z", note: null, actor_type: "user" }] },
      "/payments/pay_1/instruction-preview": { format: "MT103", simulated: true, notes: ["Preview only."], fields: [{ tag: ":20:", name: "Sender's reference", value: "pay_1", note: "x" }], pacs008: { ChrgBr: "DEBT", UETR: null, RmtInf: "x" } },
      "/kyc/status": KYC,
      "/health": { mode: "sandbox" },
    });
    const { container } = render(
      <MemoryRouter initialEntries={["/payments/pay_1"]}>
        <Routes><Route path="/payments/:paymentId" element={<PaymentScreen />} /></Routes>
      </MemoryRouter>,
    );
    await screen.findByText("Before this can be approved");
    await screen.findByText("Payment instruction preview");
    expect(await violations(container)).toEqual([]);
  });

  it("the compliance report", async () => {
    const report = { report_type: "payment_compliance_report", generated_at: "2026-10-14T10:00:00Z", synthetic: true, disclaimer: "Sandbox.", report_hash: "sha256:x",
      payment: { payment_id: "pay_1", state: "SETTLED", reference: "INV-1", provider_name: "Provider B (synthetic)", uetr: "u", due_date: "2026-10-28", latest_send_date: "2026-10-20", created_at: "2026-10-14T09:31:00Z", approved_at: null, submitted_at: null, settled_at: null, failure_reason: null },
      amount: { beneficiary_receives: "GBP 10,000.00", rate: "161.600000", charge_code: "OUR", total_cost: "BDT 25,300.00", cost_pct: "1.58", parent_pays: "BDT 1,625,300.00", shortfall: "GBP 0.00" },
      parties: { originator: { name: "Demo Parent", address: "Dhaka", country: "BD" }, beneficiary: { name: "University", account_masked: "GB** 4821", bic: "EXMPGB2L", country: "GB" } },
      approval: { approved: false, approved_by: null, approved_at: null, summary_hash: null, mfa_proof_reference: null },
      controls: [{ key: "kyc", label: "Identity check", result: "PASS", evidence: "ok" }],
      timeline: [], audit: { events: [], chain: { status: "PASS", events_checked: 1, failed_seq: null, reason: null, head: { seq: 1, hash: "c".repeat(64) } } } } as unknown as ComplianceReport;
    mockApi({ "/payments/pay_1/compliance-report": report });
    const { container } = render(
      <MemoryRouter initialEntries={["/payments/pay_1/report"]}>
        <Routes><Route path="/payments/:paymentId/report" element={<ReportScreen />} /></Routes>
      </MemoryRouter>,
    );
    await screen.findByText("Compliance report");
    expect(await violations(container)).toEqual([]);
  });

  it("the sandbox screen", async () => {
    mockApi({ "/sandbox": {
      sandbox: true, banner: "Sandbox", disclaimer: "Indicative.", ai_mode: "template",
      simulated: [{ component: "Exchange rates", what: "Synthetic." }], scenarios: [{ token: "FAIL_TEST", where: "Recipient name", effect: "Fails." }],
      providers: [{ provider_id: "prov_b", name: "Provider B (synthetic)" }],
      timings: { quote_ttl_seconds: 300, mfa_proof_ttl_seconds: 300, kyc_review_seconds: 8, submit_delay_seconds: 3, settle_delay_seconds: 5, slow_settle_delay_seconds: 30 },
      limits: { per_transaction_usd_equivalent: 50000, daily_usd_equivalent: 100000, indicative: "Sandbox caps." }, demo: null,
    } });
    const { container } = render(<MemoryRouter><SandboxScreen /></MemoryRouter>);
    await screen.findByText("Test scenarios");
    expect(await violations(container)).toEqual([]);
  });

  it("the assistant chat showing a plan card", async () => {
    mockApi({ "/assistant/chat": chatReply({ task: PLAN_CARD }) });
    const { container } = render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Ask the assistant" }));
    await userEvent.click(screen.getByRole("button", { name: "I need to pay GBP 10,000 tuition by 28 October" }));
    await screen.findByRole("region", { name: "Payment plan" });
    expect(await violations(container)).toEqual([]);
  });
});

describe("accessibility (axe): bank network", () => {
  it("the bank network screen with accounts, a form, an open transfer and the books", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: user("parent", [...BANK_PERMISSIONS, "payments:read"]), ready: true,
      login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
    });
    const transfer = bankTransfer({
      status: "SETTLED",
      steps: bankTransfer().steps.map((s) => ({ ...s, done: true })),
      events: [{
        at: "2026-10-14T09:31:00Z", stage: "ORIGINATING_BANK", bank_code: "EXMPBDA1", bank_name: "Example Bank A (sandbox)",
        event: "step_done", note: "Sent",
        message: { type: "MT103", fields: [{ tag: ":71A:", name: "Details of charges", value: "OUR" }] },
      }],
      journals: [{
        id: "jrn_1", kind: "STEP", stage: "ORIGINATING_BANK", memo: "Sell foreign currency", posted_at: "2026-10-14T09:31:00Z",
        lines: [{ side: "DEBIT", bank: "Example Bank A (sandbox)", account: "IN_FLIGHT", amount: { amount_minor: 1, currency: "BDT", formatted: "BDT 0.01" } }],
      }],
    });
    mockApi({
      "/bank/network": BANK_NETWORK, "/bank/accounts": { items: [bankAccount()], totals: BANK_TOTALS },
      "/kyc/status": KYC,
      "/bank/beneficiaries": { items: [beneficiary()] }, "/bank/transfers": { items: [transfer] },
      "/bank/transfers/btr_1": transfer, "/health": { mode: "sandbox" },
    });
    const { container } = render(<MemoryRouter><BankScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: /Open transfer to University/ }));
    await screen.findByRole("article");
    expect(await violations(container)).toEqual([]);
  });
});

describe("accessibility (axe): smart escrow", () => {
  it("the escrow screen with a plan form, a live escrow, a frozen one, anchors and the chain", async () => {
    mockApi({
      "/escrows": { items: [
        escrowView({ tranches: [tranche(0, { state: "RELEASED" }), tranche(1, { due: true }), tranche(2)] }),
        escrowView({ escrow_id: "esc_2", chain_status: "FROZEN", reference: "Held for review" }),
        escrowView({ escrow_id: "esc_3", status: "PENDING_CONFIRMATION", chain_status: null, chain: null, reference: "Next term" }),
      ] },
      "/chain/status": CHAIN_STATUS,
      "/chain/anchors": { items: [{ index: 0, seq: 12, head: "9".repeat(64), time: "2026-10-14T05:02:00Z" }] },
      "/chain/verify": verdict(),
      "/recipients": { items: [RECIPIENT] }, "/corridors": CORRIDORS, "/kyc/status": KYC,
      "/health": { mode: "sandbox" },
    });
    vi.mocked(useAuth).mockReturnValue({
      user: user("parent", [...PARENT_PERMISSIONS, "escrow:read", "escrow:write", "chain:read"]), ready: true,
      login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
    });
    const { container } = render(<MemoryRouter><EscrowScreen /></MemoryRouter>);
    await screen.findAllByRole("article");
    expect(await violations(container)).toEqual([]);
  });

  it("the reviewer's view with the freeze form, the clock and the verdict", async () => {
    mockApi({
      "/escrows": { items: [escrowView()] }, "/chain/status": CHAIN_STATUS,
      "/chain/anchors": { items: [] }, "/chain/verify": verdict({ status: "NO_ANCHOR", anchors: [] }),
      "/recipients": { items: [] }, "/corridors": CORRIDORS, "/health": { mode: "sandbox" },
    });
    vi.mocked(useAuth).mockReturnValue({
      user: user("admin", ["escrow:read", "escrow:freeze", "chain:read", "chain:anchor", "audit:verify", "sandbox:control"]),
      ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
    });
    const { container } = render(<MemoryRouter><EscrowScreen /></MemoryRouter>);
    await screen.findByRole("form", { name: /Reviewer control/ });
    await userEvent.click(screen.getByRole("button", { name: "Verify against the chain" }));
    await screen.findByText("Nothing anchored yet");
    expect(await violations(container)).toEqual([]);
  });
});
