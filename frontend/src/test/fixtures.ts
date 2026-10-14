// Synthetic API fixtures and a tiny fetch router for component tests.
import { vi } from "vitest";
import type { Mock } from "vitest";

import type { KycView, Payment, Quote, QuoteResult, Recipient, Role, UserView } from "../api/types";

export function user(role: Role, permissions: string[]): UserView {
  return {
    user_id: `usr_${role}`, email: `${role}@demo.studyroute.test`, display_name: `Demo ${role}`, role,
    kyc_status: role === "admin" ? null : "PENDING", payer: null, permissions,
  };
}

export const PARENT_PERMISSIONS = [
  "quotes:create", "quotes:read", "payments:read", "payments:draft", "payments:request_approval",
  "payments:approve", "payments:cancel", "payments:reject", "recipients:allowlist",
];
export const STUDENT_PERMISSIONS = ["quotes:create", "quotes:read", "payments:read"];

const DISPLAY = {
  provider_rate: "161.600000", margin_pct: "1.00%", cost_pct: "1.58%", fx_cost: "BDT 16,000.00",
  fixed_fee: "BDT 3,000.00", swift_fee: "BDT 1,500.00", sender_extra: "BDT 4,800.00",
  shortfall_bdt: "BDT 0.00", total_cost: "BDT 25,300.00", parent_pays: "BDT 1,625,300.00",
  intermediary_fee: "GBP 30.00", receiving_fee: "GBP 0.00", shortfall: "GBP 0.00",
  beneficiary_receives: "GBP 10,000.00",
};

export function result(rank: number, id: string, name: string, shortfallMinor = 0): QuoteResult {
  return {
    rank, provider_id: id, provider_name: name, provider_rate: "161.600000", margin_pct: "1.00",
    charge_code: shortfallMinor > 0 ? "SHA" : "OUR", requested_charge_code: "OUR",
    fees: { fixed_bdt_minor: 300000, swift_bdt_minor: 150000, intermediary_foreign_minor: 3000, receiving_foreign_minor: 0 },
    shortfall_foreign_minor: shortfallMinor, total_cost_bdt_minor: 2530000, cost_pct: "1.58",
    parent_pays_bdt_minor: 162530000, eta_business_days: 2,
    warnings: shortfallMinor > 0 ? [{ code: "SHORTFALL", message: "The university may receive less." }] : [],
    display: { ...DISPLAY, shortfall: shortfallMinor > 0 ? "GBP 35.00" : "GBP 0.00" },
  };
}

export const QUOTE: Quote = {
  quote_id: "qte_1", created_at: "2026-10-14T09:30:00Z", expires_at: "2099-01-01T00:00:00Z",
  status: "ACTIVE", seconds_left: 300, target: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
  purpose: "TUITION", destination_country: "GB", charge_code: "OUR", due_date: "2026-10-28", recipient_id: null,
  mid_rate: { value: "160.000000", source: "synthetic", as_of: "2026-10-14T09:29:50Z", display: "BDT 160.000000 per 1 GBP" },
  results: [result(1, "prov_b", "Provider B (synthetic)"), result(2, "prov_c", "Provider C (synthetic)", 3500)],
  input_hash: "sha256:abc", synthetic: true, disclaimer: "Sandbox.",
};

export const RECIPIENT: Recipient = {
  recipient_id: "rcp_1", type: "UNIVERSITY", display_name: "University of Example (synthetic)", country: "GB",
  bic: "EXMPGB2L", account_kind: "IBAN", account_masked: "GB** **** 4821", routing_code: null, label: "x",
  allowlisted: false, allowlisted_at: null, created_at: "2026-10-14T09:00:00Z",
};

export const KYC: KycView = {
  user_id: "usr_parent", status: "PENDING", message: "Your documents are being reviewed (simulated).", simulated: true,
  required_documents: [], provided_documents: [], missing: [], submitted_at: null, review_due_at: null,
};

export function payment(overrides: Partial<Payment> = {}): Payment {
  const summary = {
    payment_id: "pay_1", recipient: "University of Example (synthetic) GB** **** 4821",
    provider_name: "Provider B (synthetic)", reference: "INV-1", beneficiary_receives: { amount_minor: 1000000, currency: "GBP" },
    rate: "161.600000", charge_code: "OUR" as const, total_cost_bdt_minor: 2530000, parent_pays_bdt_minor: 162530000,
    latest_send_date: "2026-10-20", quote_expires_at: "2099-01-01T00:00:00Z", disclaimer: "Sandbox.", shortfall_foreign_minor: 0,
    display: { beneficiary_receives: "GBP 10,000.00", total_cost: "BDT 25,300.00", parent_pays: "BDT 1,625,300.00", cost_pct: "1.58%" },
  };
  return {
    payment_id: "pay_1", state: "QUOTED", target: QUOTE.target, provider_id: "prov_b", provider_name: "Provider B (synthetic)",
    recipient_label: "University of Example (synthetic) GB** **** 4821", reference: "INV-1", due_date: "2026-10-28",
    uetr: null, parent_pays: "BDT 1,625,300.00", created_at: "2026-10-14T09:31:00Z", updated_at: "2026-10-14T09:31:00Z",
    quote_id: "qte_1", quote_expires_at: "2099-01-01T00:00:00Z", quote_status: "ACTIVE", destination_country: "GB",
    purpose: "TUITION", recipient: { recipient_id: "rcp_1", label: "University of Example", allowlisted: true },
    result: result(1, "prov_b", "Provider B (synthetic)"), latest_send_date: null, summary: null, summary_hash: null,
    summary_preview: summary, approved_by: null, approved_at: null, submitted_at: null, settled_at: null,
    failure_reason: null,
    readiness: { blockers: [], can_request_approval: true, can_approve: false },
    simulated: true, disclaimer: "Sandbox.", ...overrides,
  };
}

type Handler = unknown | ((init: RequestInit | undefined) => unknown);

/** Routes fetch by path (everything after /api/v1). Unknown paths fail the test loudly. */
export function mockApi(routes: Record<string, Handler>): Mock<typeof fetch> {
  const fn = vi.fn<typeof fetch>(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace("/api/v1", "").split("?")[0] ?? "";
    if (!(path in routes)) return new Response(JSON.stringify({ code: "NOT_MOCKED", detail: path }), { status: 500 });
    const handler = routes[path];
    const body = typeof handler === "function" ? (handler as (i?: RequestInit) => unknown)(init) : handler;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function problem(status: number, code: string, detail: string): Response {
  const body = { type: "x", title: code, status, code, detail, request_id: "req_t" };
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
