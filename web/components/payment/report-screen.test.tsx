import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportScreen } from "@/components/payment/report-screen";
import type { ComplianceReport } from "@/lib/api/types";
import { canonicalJson, sha256Ref } from "@/lib/canonical";
import { mockApi, problem } from "@/tests/fixtures";
import { setLocation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

const EVENT = {
  event_id: "evt_1",
  seq: 7,
  timestamp: "2026-10-14T09:33:02Z",
  actor_type: "user",
  actor_id: "usr_demo_parent",
  action: "approval.granted",
  payment_id: "pay_1",
  quote_id: null,
  amount_minor: null,
  currency: null,
  recipient_id: null,
  decision: "approved",
  reason_code: "mfa:abc123",
  detail: null,
  input_hash: null,
  output_hash: null,
  model_version: null,
  prev_event_hash: "a".repeat(64),
  this_event_hash: "b".repeat(64),
};

const BODY = {
  report_type: "payment_compliance_report",
  generated_at: "2026-10-14T10:00:00Z",
  synthetic: true,
  disclaimer:
    "Sandbox. Synthetic data. No real money moved. Indicative. Confirm with your AD bank.",
  payment: {
    payment_id: "pay_1",
    state: "SETTLED",
    reference: "INV-1",
    provider_name: "Provider B (synthetic)",
    uetr: "7c1d4f0e-5a9b-4e3c-8a21-2b6f9d0c1e44",
    due_date: "2026-10-28",
    latest_send_date: "2026-10-20",
    created_at: "2026-10-14T09:31:00Z",
    approved_at: "2026-10-14T09:33:02Z",
    submitted_at: null,
    settled_at: "2026-10-14T09:40:00Z",
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
    originator: { name: "Demo Parent", address: "Dhaka, BD (synthetic)", country: "BD" },
    beneficiary: {
      name: "University of Example (synthetic)",
      account_masked: "GB** **** 4821",
      bic: "EXMPGB2L",
      country: "GB",
    },
  },
  approval: {
    approved: true,
    approved_by: "usr_demo_parent",
    approved_at: "2026-10-14T09:33:02Z",
    summary_hash: "sha256:abc",
    mfa_proof_reference: "mfa:abc123",
  },
  controls: [
    {
      key: "kyc",
      label: "Identity check (KYC, simulated)",
      result: "PASS",
      evidence: "Mock KYC status is VERIFIED.",
    },
    {
      key: "mfa",
      label: "Fresh MFA at approval",
      result: "NOT_YET",
      evidence: "Not approved yet.",
    },
  ],
  timeline: [
    {
      state: "SETTLED",
      at: "2026-10-14T09:40:00Z",
      note: "Credited (simulated)",
      actor_type: "provider",
    },
  ],
  audit: {
    events: [EVENT],
    chain: {
      status: "PASS",
      events_checked: 24,
      failed_seq: null,
      reason: null,
      head: { seq: 24, hash: "c".repeat(64) },
    },
  },
};

/** The report as the API seals it; `edit` changes a copy after the hash was taken, like a tamperer would. */
async function sealed(edit?: (r: typeof BODY) => void): Promise<ComplianceReport> {
  const hash = await sha256Ref(canonicalJson(BODY));
  const copy = structuredClone(BODY);
  edit?.(copy);
  return { ...copy, report_hash: hash } as unknown as ComplianceReport;
}

async function open(report: ComplianceReport) {
  mockApi({ "/payments/pay_1/compliance-report": report });
  renderWithProviders(<ReportScreen />);
  await screen.findByRole("heading", { name: "Compliance report" });
}

beforeEach(() => setLocation("/payments/report/", "id=pay_1"));
afterEach(() => vi.unstubAllGlobals());

describe("compliance report screen", () => {
  it("shows the parties, the controls with their results and the audit trail", async () => {
    await open(await sealed());
    expect(screen.getByText("GB** **** 4821")).toBeInTheDocument();
    expect(screen.getByText("Demo Parent")).toBeInTheDocument();
    const row = screen.getByText("Fresh MFA at approval").closest("tr");
    expect(within(row as HTMLElement).getByText("Not yet")).toBeInTheDocument();
    expect(screen.getByText("Pass")).toBeInTheDocument();
    expect(screen.getByText("approval.granted")).toBeInTheDocument();
    expect(screen.getByText(/24 events verified/)).toBeInTheDocument();
    expect(screen.getByText("mfa:abc123", { selector: "span" })).toBeInTheDocument();
  });

  it("confirms an untouched report in the browser", async () => {
    await open(await sealed());
    await userEvent.click(screen.getByRole("button", { name: "Verify this report in my browser" }));
    expect(await screen.findByText("Matches: not changed")).toBeInTheDocument();
  });

  it("flags a report that was edited after it was sealed", async () => {
    await open(
      await sealed((r) => {
        r.amount.parent_pays = "BDT 1.00";
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Verify this report in my browser" }));
    expect(await screen.findByText("Does not match")).toBeInTheDocument();
    expect(screen.queryByText("Matches: not changed")).toBeNull();
  });

  it("offers printing and a JSON download, and says it is a sandbox report", async () => {
    await open(await sealed());
    expect(screen.getByRole("button", { name: "Print or save as PDF" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeInTheDocument();
    expect(screen.getByText(/No real money moved/)).toBeInTheDocument();
  });

  it("links back to the payment by its id", async () => {
    await open(await sealed());
    expect(screen.getByRole("link", { name: "Back to the payment" })).toHaveAttribute(
      "href",
      "/payments/view/?id=pay_1",
    );
  });

  it("shows the server's reason and a way back when the report cannot be built", async () => {
    mockApi({
      "/payments/pay_1/compliance-report": problem(404, "NOT_FOUND", "Payment not found."),
    });
    renderWithProviders(<ReportScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Payment not found.");
    expect(screen.getByRole("link", { name: "Back to the payment" })).toBeInTheDocument();
  });
});
