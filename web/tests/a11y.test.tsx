// Automated accessibility checks (axe-core) on the main screens. jsdom cannot compute colours, so
// the contrast rule is checked separately in a real browser (scripts/tour.mjs); everything else runs here.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";
import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AssistantPanel } from "@/components/assistant/assistant-panel";
import { BankScreen } from "@/components/bank/bank-screen";
import { CompareScreen } from "@/components/compare/compare-screen";
import { DashboardScreen } from "@/components/dashboard/dashboard-screen";
import { EscrowScreen } from "@/components/escrow/escrow-screen";
import { AppShell } from "@/components/layout/app-shell";
import { SandboxBanner } from "@/components/layout/sandbox-banner";
import { PaymentScreen } from "@/components/payment/payment-screen";
import { ReportScreen } from "@/components/payment/report-screen";
import { useAuth } from "@/components/providers/auth-provider";
import { RecipientsScreen } from "@/components/recipients/recipients-screen";
import { SandboxScreen } from "@/components/sandbox/sandbox-screen";
import { resetHealthCache } from "@/lib/api/health";
import type { ComplianceReport, Role } from "@/lib/api/types";
import {
  BANK_NETWORK,
  BANK_PERMISSIONS,
  BANK_TOTALS,
  CHAIN_STATUS,
  KYC,
  PARENT_PERMISSIONS,
  PLAN_VIEW,
  PLAN_CARD,
  QUOTE,
  RECIPIENT,
  SEND_PLAN,
  STRESS,
  bankAccount,
  bankTransfer,
  beneficiary,
  chatReply,
  corridor,
  escrowView,
  mockApi,
  payment,
  tranche,
  user,
  verdict,
} from "@/tests/fixtures";
import { setLocation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

async function violations(container: HTMLElement): Promise<string[]> {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map(
    (v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}

function signIn(role: Role, permissions: string[]) {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
  });
}

beforeEach(() => {
  resetHealthCache();
  signIn("parent", [...PARENT_PERMISSIONS, "audit:read", "planner:read", "data:reset"]);
});
afterEach(() => vi.unstubAllGlobals());

const CORRIDORS = { items: [corridor()], providers: [] };
const TRACKER = {
  payment_id: "pay_1",
  uetr: null,
  state: "QUOTED",
  host_rail: "UK Faster Payments",
  simulated: true,
  timeline: [{ state: "QUOTED", at: "2026-10-14T09:31:00Z", note: null, actor_type: "user" }],
};
const PREVIEW = {
  format: "MT103",
  simulated: true,
  notes: ["Preview only."],
  fields: [{ tag: ":20:", name: "Sender's reference", value: "pay_1", note: "x" }],
  pacs008: { ChrgBr: "DEBT", UETR: null, RmtInf: "x" },
};

describe("accessibility (axe)", () => {
  it("the harness really catches a defect, so a pass means something", async () => {
    const { container } = render(
      <div>
        <button type="button" />
        <input />
      </div>,
    );
    const found = (await violations(container)).map((v) => v.split(":")[0]);
    expect(found).toEqual(expect.arrayContaining(["button-name", "label"]));
  });

  it("the sandbox banner is a named notice", async () => {
    const { container } = render(<SandboxBanner />);
    expect(screen.getByRole("alert", { name: "Sandbox notice" })).toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
  });

  it("the sign-in page", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      ready: true,
      login: vi.fn(),
      logout: vi.fn(),
      reloadUser: vi.fn(),
    });
    mockApi({
      "/health": {
        status: "ok",
        mode: "sandbox",
        ai_mode: "template",
        demo: { accounts: ["parent@demo.studyroute.test"], password: "pw", mfa_code: "246810" },
      },
    });
    const { container } = renderWithProviders(<LoginPage />);
    await screen.findByText("parent@demo.studyroute.test");
    expect(await violations(container)).toEqual([]);
  });

  it("the signed-in frame: skip link, sidebar, top bar and page", async () => {
    setLocation("/compare/");
    mockApi({});
    const { container } = renderWithProviders(
      <AppShell>
        <h1>Page</h1>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
  });

  it("the dashboard with every card", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/kyc/status": KYC,
      "/payments": { items: [], next_cursor: null },
      "/planner/deadline": {
        due_date: "2026-10-28",
        latest_send_date: "2026-10-20",
        recommended_send_date: "2026-10-19",
        earliest_send_date: "2026-10-16",
        status: "ON_TRACK",
        days_until_latest_send: 4,
        settlement_business_days: 3,
        buffer_days: 2,
        bank_cutoff_local: "15:00",
        skipped_days: [],
        warnings: [],
        indicative: "Indicative.",
        destination_country: "GB",
      },
      "/planner/runway": {
        display: {
          amount: "GBP 5,000.00",
          monthly_cost: "GBP 1,200.00",
          covers: "4.1 months",
          full_months: "4",
          leftover: "GBP 200.00",
        },
        monthly_cost_usd_equivalent: "USD 1,560.00",
        reference: {
          label: "Reference",
          value: "GBP 1,300.00",
          verified: false,
          badge: "NOT_VERIFIED",
          note: "n",
        },
      },
      "/planner/send-plan": SEND_PLAN,
      "/rates/history": {
        currency: "GBP",
        source: "synthetic",
        disclaimer: "Synthetic.",
        points: [
          { date: "2026-10-12", rate: "159.5" },
          { date: "2026-10-13", rate: "160.5" },
        ],
        hint: {
          kind: "NEUTRAL",
          today: "160.5",
          average: "160.0",
          gap_pct: "0.3",
          days: 2,
          message: "About average.",
        },
      },
    });
    const { container } = renderWithProviders(<DashboardScreen />);
    await screen
      .findByText("Fifteen days around the deadline", { exact: false }, { timeout: 4000 })
      .catch(() => undefined);
    await screen.findByText("months of living costs covered");
    await screen.findByText("About average");
    expect(await violations(container)).toEqual([]);
  });

  it("the compare screen before any quote: form, charge code cards, summary and the empty quotes card", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [RECIPIENT] },
      "/planner/deadline": PLAN_VIEW,
    });
    const { container } = renderWithProviders(<CompareScreen />);
    await screen.findByText("On track");
    expect(await violations(container)).toEqual([]);
  });

  it("the compare screen with results, the stress test and the breakdown sheet", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [RECIPIENT] },
      "/quotes": QUOTE,
      "/quotes/qte_1/stress": STRESS,
      "/planner/deadline": PLAN_VIEW,
    });
    const { container } = renderWithProviders(<CompareScreen />);
    const button = await screen.findByRole("button", { name: "Get quotes" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await screen.findByRole("region", { name: "Provider comparison table" });
    await screen.findByText("Currency-drop stress test");
    expect(await violations(container)).toEqual([]);

    await userEvent.click(
      screen.getByRole("button", { name: "Actions for Provider B (synthetic)" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "View breakdown" }));
    const sheet = await screen.findByRole("dialog", { name: "Provider B (synthetic)" });
    expect(await violations(sheet)).toEqual([]);
  });

  it("the recipients screen", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [RECIPIENT] },
      "/health": { mode: "sandbox" },
    });
    const { container } = renderWithProviders(<RecipientsScreen />);
    await screen.findByText("GB** **** 4821");
    expect(await violations(container)).toEqual([]);
  });

  it("a payment with its summary, blockers, preview and tracker", async () => {
    setLocation("/payments/view/", "id=pay_1");
    mockApi({
      "/payments/pay_1": payment({
        readiness: {
          blockers: [{ code: "KYC_NOT_VERIFIED", message: "KYC is not verified (simulated)." }],
          can_request_approval: false,
          can_approve: false,
        },
      }),
      "/payments/pay_1/tracker": TRACKER,
      "/payments/pay_1/instruction-preview": PREVIEW,
      "/kyc/status": KYC,
      "/health": { mode: "sandbox" },
    });
    const { container } = renderWithProviders(<PaymentScreen />);
    await screen.findByText("Before this can be approved");
    await screen.findByText("Payment instruction preview");
    expect(await violations(container)).toEqual([]);
  });

  it("the compliance report", async () => {
    setLocation("/payments/report/", "id=pay_1");
    const report = {
      report_type: "payment_compliance_report",
      generated_at: "2026-10-14T10:00:00Z",
      synthetic: true,
      disclaimer: "Sandbox.",
      report_hash: "sha256:x",
      payment: {
        payment_id: "pay_1",
        state: "SETTLED",
        reference: "INV-1",
        provider_name: "Provider B (synthetic)",
        uetr: "u",
        due_date: "2026-10-28",
        latest_send_date: "2026-10-20",
        created_at: "2026-10-14T09:31:00Z",
        approved_at: null,
        submitted_at: null,
        settled_at: null,
        failure_reason: null,
      },
      amount: {
        beneficiary_receives: "GBP 10,000.00",
        rate: "161.600000",
        charge_code: "OUR",
        total_cost: "BDT 25,300.00",
        cost_pct: "1.58",
        parent_pays: "BDT 1,625,300.00",
        shortfall: "GBP 0.00",
      },
      parties: {
        originator: { name: "Demo Parent", address: "Dhaka", country: "BD" },
        beneficiary: {
          name: "University",
          account_masked: "GB** 4821",
          bic: "EXMPGB2L",
          country: "GB",
        },
      },
      approval: {
        approved: false,
        approved_by: null,
        approved_at: null,
        summary_hash: null,
        mfa_proof_reference: null,
      },
      controls: [{ key: "kyc", label: "Identity check", result: "PASS", evidence: "ok" }],
      timeline: [],
      audit: {
        events: [],
        chain: {
          status: "PASS",
          events_checked: 1,
          failed_seq: null,
          reason: null,
          head: { seq: 1, hash: "c".repeat(64) },
        },
      },
    } as unknown as ComplianceReport;
    mockApi({ "/payments/pay_1/compliance-report": report });
    const { container } = renderWithProviders(<ReportScreen />);
    await screen.findByRole("heading", { name: "Compliance report" });
    expect(await violations(container)).toEqual([]);
  });

  it("the sandbox screen", async () => {
    mockApi({
      "/sandbox": {
        sandbox: true,
        banner: "Sandbox",
        disclaimer: "Indicative.",
        ai_mode: "template",
        simulated: [{ component: "Exchange rates", what: "Synthetic." }],
        scenarios: [{ token: "FAIL_TEST", where: "Recipient name", effect: "Fails." }],
        providers: [{ provider_id: "prov_b", name: "Provider B (synthetic)" }],
        timings: {
          quote_ttl_seconds: 300,
          mfa_proof_ttl_seconds: 300,
          kyc_review_seconds: 8,
          submit_delay_seconds: 3,
          settle_delay_seconds: 5,
          slow_settle_delay_seconds: 30,
        },
        limits: {
          per_transaction_usd_equivalent: 50000,
          daily_usd_equivalent: 100000,
          indicative: "Sandbox caps.",
        },
        demo: null,
      },
      "/payments": { items: [], next_cursor: null },
    });
    const { container } = renderWithProviders(<SandboxScreen />);
    await screen.findByText("Test scenarios");
    expect(await violations(container)).toEqual([]);
  });

  it("the assistant chat showing a plan card", async () => {
    mockApi({ "/assistant/chat": chatReply({ task: PLAN_CARD }) });
    const { container } = renderWithProviders(
      <AssistantProvider>
        <AssistantPanel />
      </AssistantProvider>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "I need to pay GBP 10,000 tuition by 28 October" }),
    );
    await screen.findByRole("region", { name: "Payment plan" });
    expect(await violations(container)).toEqual([]);
  });
});

describe("accessibility (axe): bank network", () => {
  it("the bank network screen with accounts, a form, an open transfer and the books", async () => {
    signIn("parent", [...BANK_PERMISSIONS, "payments:read"]);
    const transfer = bankTransfer({
      status: "SETTLED",
      steps: bankTransfer().steps.map((s) => ({ ...s, done: true })),
      events: [
        {
          at: "2026-10-14T09:31:00Z",
          stage: "ORIGINATING_BANK",
          bank_code: "EXMPBDA1",
          bank_name: "Example Bank A (sandbox)",
          event: "step_done",
          note: "Sent",
          message: {
            type: "MT103",
            fields: [{ tag: ":71A:", name: "Details of charges", value: "OUR" }],
          },
        },
      ],
      journals: [
        {
          id: "jrn_1",
          kind: "STEP",
          stage: "ORIGINATING_BANK",
          memo: "Sell foreign currency",
          posted_at: "2026-10-14T09:31:00Z",
          lines: [
            {
              side: "DEBIT",
              bank: "Example Bank A (sandbox)",
              account: "IN_FLIGHT",
              amount: { amount_minor: 1, currency: "BDT", formatted: "BDT 0.01" },
            },
          ],
        },
      ],
    });
    mockApi({
      "/bank/network": BANK_NETWORK,
      "/bank/accounts": { items: [bankAccount()], totals: BANK_TOTALS },
      "/kyc/status": KYC,
      "/bank/beneficiaries": { items: [beneficiary()] },
      "/bank/transfers": { items: [transfer] },
      "/bank/transfers/btr_1": transfer,
      "/health": { mode: "sandbox" },
    });
    const { container } = renderWithProviders(<BankScreen />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Open transfer to University/ }),
    );
    await screen.findByRole("region", { name: /BDT 1,630,000.00 to University/ });
    expect(await violations(container)).toEqual([]);
  });
});

describe("accessibility (axe): smart escrow", () => {
  it("the escrow screen with a plan form, a live escrow, a frozen one, anchors and the chain", async () => {
    mockApi({
      "/escrows": {
        items: [
          escrowView({
            tranches: [tranche(0, { state: "RELEASED" }), tranche(1, { due: true }), tranche(2)],
          }),
          escrowView({ escrow_id: "esc_2", chain_status: "FROZEN", reference: "Held for review" }),
          escrowView({
            escrow_id: "esc_3",
            status: "PENDING_CONFIRMATION",
            chain_status: null,
            chain: null,
            reference: "Next term",
          }),
        ],
      },
      "/chain/status": CHAIN_STATUS,
      "/chain/anchors": {
        items: [{ index: 0, seq: 12, head: "9".repeat(64), time: "2026-10-14T05:02:00Z" }],
      },
      "/chain/verify": verdict(),
      "/recipients": { items: [RECIPIENT] },
      "/corridors": CORRIDORS,
      "/kyc/status": KYC,
      "/health": { mode: "sandbox" },
    });
    signIn("parent", [...PARENT_PERMISSIONS, "escrow:read", "escrow:write", "chain:read"]);
    const { container } = renderWithProviders(<EscrowScreen />);
    await screen.findAllByRole("region", { name: /^Escrow / });
    expect(await violations(container)).toEqual([]);
  });

  it("the reviewer's view with the freeze form, the clock and the verdict", async () => {
    mockApi({
      "/escrows": { items: [escrowView()] },
      "/chain/status": CHAIN_STATUS,
      "/chain/anchors": { items: [] },
      "/chain/verify": verdict({ status: "NO_ANCHOR", anchors: [] }),
      "/recipients": { items: [] },
      "/corridors": CORRIDORS,
      "/health": { mode: "sandbox" },
    });
    signIn("admin", [
      "escrow:read",
      "escrow:freeze",
      "chain:read",
      "chain:anchor",
      "audit:verify",
      "sandbox:control",
    ]);
    const { container } = renderWithProviders(<EscrowScreen />);
    await screen.findByRole("form", { name: /Reviewer control/ });
    await userEvent.click(screen.getByRole("button", { name: "Verify against the chain" }));
    await screen.findByText("Nothing anchored yet");
    expect(await violations(container)).toEqual([]);
  });
});
