// Synthetic API fixtures and a tiny fetch router for component tests.
import { vi } from "vitest";
import type { Mock } from "vitest";

import type {
  BankAccountView,
  BankNetwork,
  BankTransfer,
  Beneficiary,
  KycView,
  Payment,
  Quote,
  QuoteResult,
  Recipient,
  Role,
  UserView,
} from "@/lib/api/types";

export function user(role: Role, permissions: string[]): UserView {
  return {
    user_id: `usr_${role}`,
    email: `${role}@demo.studyroute.test`,
    display_name: `Demo ${role}`,
    role,
    kyc_status: role === "admin" ? null : "PENDING",
    payer: null,
    permissions,
  };
}

export const PARENT_PERMISSIONS = [
  "quotes:create",
  "quotes:read",
  "payments:read",
  "payments:draft",
  "payments:request_approval",
  "payments:approve",
  "payments:cancel",
  "payments:reject",
  "recipients:allowlist",
];
export const STUDENT_PERMISSIONS = ["quotes:create", "quotes:read", "payments:read"];

const DISPLAY = {
  provider_rate: "161.600000",
  margin_pct: "1.00%",
  cost_pct: "1.58%",
  fx_cost: "BDT 16,000.00",
  fixed_fee: "BDT 3,000.00",
  swift_fee: "BDT 1,500.00",
  sender_extra: "BDT 4,800.00",
  shortfall_bdt: "BDT 0.00",
  total_cost: "BDT 25,300.00",
  parent_pays: "BDT 1,625,300.00",
  intermediary_fee: "GBP 30.00",
  receiving_fee: "GBP 0.00",
  shortfall: "GBP 0.00",
  beneficiary_receives: "GBP 10,000.00",
};

export function result(rank: number, id: string, name: string, shortfallMinor = 0): QuoteResult {
  return {
    rank,
    provider_id: id,
    provider_name: name,
    provider_rate: "161.600000",
    margin_pct: "1.00",
    charge_code: shortfallMinor > 0 ? "SHA" : "OUR",
    requested_charge_code: "OUR",
    fees: {
      fixed_bdt_minor: 300000,
      swift_bdt_minor: 150000,
      intermediary_foreign_minor: 3000,
      receiving_foreign_minor: 0,
    },
    shortfall_foreign_minor: shortfallMinor,
    total_cost_bdt_minor: 2530000,
    cost_pct: "1.58",
    parent_pays_bdt_minor: 162530000,
    eta_business_days: 2,
    warnings:
      shortfallMinor > 0
        ? [{ code: "SHORTFALL", message: "The university may receive less." }]
        : [],
    display: { ...DISPLAY, shortfall: shortfallMinor > 0 ? "GBP 35.00" : "GBP 0.00" },
  };
}

export const QUOTE: Quote = {
  quote_id: "qte_1",
  created_at: "2026-10-14T09:30:00Z",
  expires_at: "2099-01-01T00:00:00Z",
  status: "ACTIVE",
  seconds_left: 300,
  target: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
  purpose: "TUITION",
  destination_country: "GB",
  charge_code: "OUR",
  due_date: "2026-10-28",
  recipient_id: null,
  mid_rate: {
    value: "160.000000",
    source: "synthetic",
    as_of: "2026-10-14T09:29:50Z",
    display: "BDT 160.000000 per 1 GBP",
  },
  results: [
    result(1, "prov_b", "Provider B (synthetic)"),
    result(2, "prov_c", "Provider C (synthetic)", 3500),
  ],
  input_hash: "sha256:abc",
  synthetic: true,
  disclaimer: "Sandbox.",
};

export const RECIPIENT: Recipient = {
  recipient_id: "rcp_1",
  type: "UNIVERSITY",
  display_name: "University of Example (synthetic)",
  country: "GB",
  bic: "EXMPGB2L",
  account_kind: "IBAN",
  account_masked: "GB** **** 4821",
  routing_code: null,
  label: "x",
  allowlisted: false,
  allowlisted_at: null,
  created_at: "2026-10-14T09:00:00Z",
};

export const KYC: KycView = {
  user_id: "usr_parent",
  status: "PENDING",
  message: "Your documents are being reviewed (simulated).",
  simulated: true,
  required_documents: [],
  provided_documents: [],
  missing: [],
  submitted_at: null,
  review_due_at: null,
};

export function payment(overrides: Partial<Payment> = {}): Payment {
  const summary = {
    payment_id: "pay_1",
    recipient: "University of Example (synthetic) GB** **** 4821",
    provider_name: "Provider B (synthetic)",
    reference: "INV-1",
    beneficiary_receives: { amount_minor: 1000000, currency: "GBP" },
    rate: "161.600000",
    charge_code: "OUR" as const,
    total_cost_bdt_minor: 2530000,
    parent_pays_bdt_minor: 162530000,
    latest_send_date: "2026-10-20",
    quote_expires_at: "2099-01-01T00:00:00Z",
    disclaimer: "Sandbox.",
    shortfall_foreign_minor: 0,
    display: {
      beneficiary_receives: "GBP 10,000.00",
      total_cost: "BDT 25,300.00",
      parent_pays: "BDT 1,625,300.00",
      cost_pct: "1.58%",
    },
  };
  return {
    payment_id: "pay_1",
    state: "QUOTED",
    target: QUOTE.target,
    provider_id: "prov_b",
    provider_name: "Provider B (synthetic)",
    recipient_label: "University of Example (synthetic) GB** **** 4821",
    reference: "INV-1",
    due_date: "2026-10-28",
    uetr: null,
    parent_pays: "BDT 1,625,300.00",
    created_at: "2026-10-14T09:31:00Z",
    updated_at: "2026-10-14T09:31:00Z",
    quote_id: "qte_1",
    quote_expires_at: "2099-01-01T00:00:00Z",
    quote_status: "ACTIVE",
    destination_country: "GB",
    purpose: "TUITION",
    recipient: { recipient_id: "rcp_1", label: "University of Example", allowlisted: true },
    result: result(1, "prov_b", "Provider B (synthetic)"),
    latest_send_date: null,
    summary: null,
    summary_hash: null,
    summary_preview: summary,
    approved_by: null,
    approved_at: null,
    submitted_at: null,
    settled_at: null,
    failure_reason: null,
    readiness: { blockers: [], can_request_approval: true, can_approve: false },
    simulated: true,
    disclaimer: "Sandbox.",
    ...overrides,
  };
}

type Handler = unknown | ((init: RequestInit | undefined) => unknown);

/** Routes fetch by path (everything after /api/v1). Unknown paths fail the test loudly. */
export function mockApi(routes: Record<string, Handler>): Mock<typeof fetch> {
  const fn = vi.fn<typeof fetch>(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace("/api/v1", "").split("?")[0] ?? "";
    // Every signed-in assistant loads non-secret saved-connection metadata.
    if (!(path in routes) && path === "/assistant/connection" && init?.method === "GET")
      return new Response(JSON.stringify({ saved: false }), { status: 200 });
    if (!(path in routes))
      return new Response(JSON.stringify({ code: "NOT_MOCKED", detail: path }), { status: 500 });
    const handler = routes[path];
    const body =
      typeof handler === "function" ? (handler as (i?: RequestInit) => unknown)(init) : handler;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function problem(status: number, code: string, detail: string): Response {
  const body = { type: "x", title: code, status, code, detail, request_id: "req_t" };
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

import type { ChatResponse, PaymentPlanCard, SendPlan, StressTest } from "@/lib/api/types";

export const PLAN_CARD: PaymentPlanCard = {
  kind: "payment_plan",
  status: "ready",
  request: {
    amount: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
    purpose: "TUITION",
    country: "GB",
    country_name: "United Kingdom",
    due_date: "2026-10-28",
    charge_code: "OUR",
  },
  quote: { quote_id: "qte_plan1", expires_at: "2099-01-01T00:00:00Z" },
  best: {
    provider_id: "prov_b",
    provider_name: "Provider B (synthetic)",
    cost_pct: "1.58%",
    parent_pays: "BDT 1,625,300.00",
    total_cost: "BDT 25,300.00",
    shortfall: "GBP 0.00",
    has_shortfall: false,
    charge_code: "OUR",
    eta_business_days: 2,
  },
  alternatives: [
    {
      provider_id: "prov_c",
      provider_name: "Provider C (synthetic)",
      cost_pct: "1.63%",
      parent_pays: "BDT 1,620,500.00",
      total_cost: "BDT 26,100.00",
      shortfall: "GBP 35.00",
      has_shortfall: true,
      charge_code: "SHA",
      eta_business_days: 3,
    },
  ],
  deadline: {
    due_date: "2026-10-28",
    latest_send_date: "2026-10-20",
    recommended_send_date: "2026-10-19",
    status: "ON_TRACK",
  },
  recipients: [],
  steps: [
    {
      key: "quote",
      label: "Quote made from your request",
      state: "done",
      detail: "Valid for 5 minutes",
      link: null,
    },
    {
      key: "deadline",
      label: "Deadline planned",
      state: "done",
      detail: "Send by 2026-10-20",
      link: null,
    },
    {
      key: "kyc",
      label: "Identity check (simulated)",
      state: "todo",
      detail: "Documents are missing.",
      link: "/",
    },
    {
      key: "recipient",
      label: "Recipient ready",
      state: "todo",
      detail: "Add the university as a recipient",
      link: "/recipients",
    },
    {
      key: "documents",
      label: "Documents ready",
      state: "todo",
      detail: "0 of 9 documents ready",
      link: "/documents",
    },
    {
      key: "draft",
      label: "Create the draft",
      state: "todo",
      detail: "You confirm the recipient and the payment reference",
      link: "/compare?quote=qte_plan1&provider=prov_b",
    },
    {
      key: "approve",
      label: "Approve",
      state: "todo",
      detail: "Only you can, with a fresh MFA code",
      link: null,
    },
  ],
  draft: {
    quote_id: "qte_plan1",
    provider_id: "prov_b",
    recipient_id: null,
    missing: ["reference", "recipient_id"],
  },
};

const OPTION = {
  charge_code: "OUR" as const,
  shortfall_foreign_minor: 0,
  exceeds_sandbox_cap: false,
};
export const SEND_PLAN: SendPlan = {
  total: { amount_minor: 1200000, currency: "GBP", formatted: "GBP 12,000.00" },
  months: 12,
  cheapest_key: "upfront",
  options: [
    {
      ...OPTION,
      key: "monthly",
      label: "Every month",
      transfers: 12,
      provider_id: "prov_a",
      provider_name: "Provider A (synthetic)",
      display: {
        per_transfer: "GBP 1,000.00",
        total_cost: "BDT 68,400.00",
        parent_pays: "BDT 1",
        avg_cost_pct: "3.56%",
        saving_vs_monthly: "BDT 0.00",
      },
    },
    {
      ...OPTION,
      key: "upfront",
      label: "All at once",
      transfers: 1,
      provider_id: "prov_b",
      provider_name: "Provider B (synthetic)",
      display: {
        per_transfer: "GBP 12,000.00",
        total_cost: "BDT 28,500.00",
        parent_pays: "BDT 2",
        avg_cost_pct: "1.48%",
        saving_vs_monthly: "BDT 39,900.00",
      },
    },
  ],
  synthetic: true,
  disclaimer: "Synthetic rates and fees. Indicative. Confirm with your AD bank.",
  trade_off:
    "Sending less often costs less in fixed fees, but moves money before it is needed. StudyRoute does not predict exchange rates.",
};

export function chatReply(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    reply: "I made a quote.",
    facts_used: [],
    facts: [],
    guard: { status: "passed", flags: [], failure: null, retries: 0 },
    proposed_actions: [],
    task: null,
    mode: "template",
    model_version: "template-v1",
    disclaimer: "Sandbox.",
    debug: { masked_prompt: "FACTS", note: "masked" },
    understanding: {
      source: "rules",
      model: null,
      model_sha256: null,
      intent: "PLAN",
      model_intent: null,
      confidence: null,
      attack: false,
      out_of_scope: false,
      continued_earlier_task: false,
      spans: [],
      values: {
        amount_minor: null,
        currency: null,
        due_date: null,
        months: null,
        charge_code: "OUR",
        purpose: "TUITION",
      },
      conflicts: [],
      unreadable: [],
    },
    dialogue: null,
    ...overrides,
  };
}

// --- sandbox bank network ---------------------------------------------------------------------
export const BANK_PERMISSIONS = ["bank:read", "bank:transfer"];

const money = (amount_minor: number, currency: string, formatted: string) => ({
  amount_minor,
  currency,
  formatted,
});

export function bankAccount(overrides: Partial<BankAccountView> = {}): BankAccountView {
  return {
    id: "bacc_parent_a",
    bank_code: "EXMPBDA1",
    bank_name: "Example Bank A (sandbox)",
    country: "BD",
    kind: "CUSTOMER",
    number: "SBX-A-0001",
    holder: "Demo Parent (synthetic)",
    label: "Parent salary account",
    currency: "BDT",
    balance: money(500_000_000, "BDT", "BDT 5,000,000.00"),
    household: true,
    simulated: true,
    ...overrides,
  };
}

export function beneficiary(overrides: Partial<Beneficiary> = {}): Beneficiary {
  const { balance: _balance, ...rest } = bankAccount({
    id: "bacc_uni",
    bank_code: "EXMPGB2L",
    bank_name: "University Bank of Example (sandbox)",
    country: "GB",
    number: "GB08EXMP12345612344821",
    holder: "University of Example (synthetic)",
    label: "University tuition account",
    currency: "GBP",
    household: false,
  });
  return { ...rest, ...overrides };
}

export function bankTransfer(overrides: Partial<BankTransfer> = {}): BankTransfer {
  return {
    id: "btr_1",
    status: "PENDING_CONFIRMATION",
    kind: "INTERNATIONAL",
    rail: "SWIFT",
    reference: "Sandbox transfer",
    uetr: "11111111-2222-4333-8444-555555555555",
    source: bankAccount(),
    destination: beneficiary(),
    debit: money(163_000_000, "BDT", "BDT 1,630,000.00"),
    credit: money(1_000_000, "GBP", "GBP 10,000.00"),
    fee: money(250_000, "BDT", "BDT 2,500.00"),
    figures: {
      you_pay: money(163_000_000, "BDT", "BDT 1,630,000.00"),
      beneficiary_receives: money(1_000_000, "GBP", "GBP 10,000.00"),
      charge_code: "OUR",
      provider_rate: "163.200000",
      bank_fees: money(250_000, "BDT", "BDT 2,500.00"),
      intermediary_fee: money(0, "GBP", "GBP 0.00"),
      receiving_fee: money(0, "GBP", "GBP 0.00"),
      total_cost: money(3_450_000, "BDT", "BDT 34,500.00"),
      cost_pct: "2.16",
    },
    plan_hash: "hash",
    next_step_at: null,
    failure_reason: null,
    created_at: "2026-10-14T09:30:00Z",
    confirmed_at: null,
    settled_at: null,
    blockers: [],
    simulated: true,
    note: "Simulated. No real bank is contacted and no real money moves.",
    steps: [
      {
        stage: "ORIGINATING_BANK",
        bank: "EXMPBDA1",
        bank_name: "Example Bank A (sandbox)",
        summary: "Originating bank sells currency and sends MT103",
        delay_seconds: 4,
        done: false,
        message: "MT103",
      },
      {
        stage: "CORRESPONDENT",
        bank: "EXMPUS6C",
        bank_name: "Example Correspondent Bank (sandbox)",
        summary: "Correspondent forwards through its nostro",
        delay_seconds: 4,
        done: false,
        message: "MT103",
      },
      {
        stage: "BENEFICIARY_BANK",
        bank: "EXMPGB2L",
        bank_name: "University Bank of Example (sandbox)",
        summary: "Beneficiary bank credits the customer",
        delay_seconds: 4,
        done: false,
        message: "CREDIT_ADVICE",
      },
    ],
    events: [],
    journals: [],
    ...overrides,
  };
}

export const BANK_TOTALS = {
  by_currency: [
    {
      currency: "BDT",
      accounts: 3,
      balance: money(1_500_000_000, "BDT", "BDT 15,000,000.00"),
      bdt_equivalent: money(1_500_000_000, "BDT", "BDT 15,000,000.00"),
    },
    {
      currency: "GBP",
      accounts: 1,
      balance: money(80_000, "GBP", "GBP 800.00"),
      bdt_equivalent: money(12_800_000, "BDT", "BDT 128,000.00"),
    },
  ],
  bdt_total: money(1_512_800_000, "BDT", "BDT 15,128,000.00"),
  note: "Converted at synthetic mid-market rates. Not a live FX feed. Indicative. Confirm with your AD bank.",
};

export const BANK_NETWORK: BankNetwork = {
  ready: true,
  simulated: true,
  all_ok: true,
  directory: {
    banks: [{ code: "EXMPBDA1", name: "Example Bank A (sandbox)", role: "AD_BANK" }],
    rails: {
      BDT: [
        {
          code: "INSTANT",
          label: "Instant payment (simulated)",
          fee_fixed_minor: 500,
          fee_bps: 0,
          min_minor: 100,
          max_minor: 50_000_000,
          seconds: 3,
        },
        {
          code: "BATCH",
          label: "Next-batch transfer (simulated)",
          fee_fixed_minor: 200,
          fee_bps: 0,
          min_minor: 100,
          max_minor: 500_000_000,
          seconds: 26,
        },
      ],
    },
    note: "Invented banks.",
  },
  trial_balance: { BDT: { debits: 1000, credits: 1000, balanced: true } },
  mirror_accounts: [
    {
      kind: "NOSTRO",
      holder_bank_name: "Example Bank A (sandbox)",
      other_name: "Example Correspondent Bank (sandbox)",
      currency: "GBP",
      balance: money(1_000_000_000, "GBP", "GBP 10,000,000.00"),
      reconciled: true,
    },
  ],
  accounts_not_matching_entries: 0,
};

import type { Corridor } from "@/lib/api/types";

/** A destination as the API lists it. Defaults describe the United Kingdom. */
export function corridor(overrides: Partial<Corridor> = {}): Corridor {
  return {
    country: "GB",
    name: "United Kingdom",
    currency: "GBP",
    account_scheme: "IBAN_OR_UK_DOMESTIC",
    host_rail: "x",
    mid_rate: "160",
    exponent: 2,
    featured: true,
    restricted: false,
    sample_amount: "10000",
    ...overrides,
  };
}

import type { AnchorVerdict, ChainStatus, EscrowTranche, EscrowView } from "@/lib/api/types";

const GBP = (minor: number) => ({
  amount_minor: minor,
  currency: "GBP",
  formatted: `GBP ${(minor / 100).toLocaleString("en-GB", { minimumFractionDigits: 2 })}`,
});

/** One tranche as the API lists it. */
export function tranche(index: number, overrides: Partial<EscrowTranche> = {}): EscrowTranche {
  return {
    index,
    amount: GBP(30_000),
    release_on: `2026-1${index}-28`,
    state: "LOCKED",
    due: false,
    ...overrides,
  };
}

/** A live escrow of three monthly tranches, as `GET /escrows` returns it. */
export function escrowView(overrides: Partial<EscrowView> = {}): EscrowView {
  return {
    escrow_id: "esc_1",
    status: "ON_CHAIN",
    chain_status: "ACTIVE",
    purpose: "LIVING",
    cadence: "MONTHLY",
    currency: "GBP",
    total: GBP(90_000),
    reference: "Fall living costs",
    recipient: { recipient_id: "rcp_1", label: "University of Example (synthetic) GB** **** 4821" },
    tranches: [
      tranche(0, { release_on: "2026-10-28" }),
      tranche(1, { release_on: "2026-11-28" }),
      tranche(2, { release_on: "2026-12-28" }),
    ],
    plan_hash: "a".repeat(64),
    created_at: "2026-10-14T05:00:00Z",
    confirmed_at: "2026-10-14T05:01:00Z",
    chain: {
      escrow_id: 1,
      contract: "0x" + "1".repeat(40),
      token: "0x" + "2".repeat(40),
      payer_wallet: "0x" + "3".repeat(40),
      beneficiary_wallet: "0x" + "4".repeat(40),
      locked: GBP(90_000),
      chain_time: "2026-10-14T05:01:00Z",
    },
    transactions: [
      {
        seq: 4,
        tx_hash: "b".repeat(64),
        kind: "CALL",
        contract: "token:GBP",
        function: "mint",
        sender: "bank",
        time: "2026-10-14T05:01:00Z",
      },
      {
        seq: 6,
        tx_hash: "c".repeat(64),
        kind: "CALL",
        contract: "escrow",
        function: "create",
        sender: "user:usr_demo_parent",
        time: "2026-10-14T05:01:00Z",
      },
    ],
    blockers: [],
    simulated: true,
    ...overrides,
  };
}

export const CHAIN_STATUS: ChainStatus = {
  simulated: true,
  engine: "py-evm, an in-memory EVM. No network, no peers, no real tokens.",
  ready: true,
  block: 6,
  chain_time: "2026-10-14T05:01:00Z",
  time_offset_seconds: 0,
  contracts: [
    {
      label: "escrow",
      contract: "TuitionEscrow",
      address: "0x" + "5".repeat(40),
      source_file: "contracts/src/TuitionEscrow.sol",
      source_sha256: "d".repeat(64),
      solc: "0.8.37",
    },
    {
      label: "anchor",
      contract: "AuditAnchor",
      address: "0x" + "6".repeat(40),
      source_file: "contracts/src/AuditAnchor.sol",
      source_sha256: "e".repeat(64),
      solc: "0.8.37",
    },
  ],
  log: { transactions: 6, head: "f".repeat(64) },
  integrity: { ok: true, problem: null },
};

export function verdict(overrides: Partial<AnchorVerdict> = {}): AnchorVerdict {
  return {
    status: "PASS",
    simulated: true,
    failed: [],
    anchors: [
      {
        index: 0,
        seq: 12,
        head: "9".repeat(64),
        time: "2026-10-14T05:02:00Z",
        database_hash: "9".repeat(64),
        state: "MATCH",
      },
    ],
    audit_chain: {
      status: "PASS",
      events_checked: 14,
      failed_seq: null,
      reason: null,
      head: { seq: 14, hash: "8".repeat(64) },
    },
    ...overrides,
  };
}

export const STRESS: StressTest = {
  quote_id: "qte_1",
  provider_id: "prov_b",
  provider_name: "Provider B (synthetic)",
  target: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
  baseline: {
    mid_rate: "160.000000",
    parent_pays_bdt_minor: 162530000,
    display: { parent_pays: "BDT 1,625,300.00", provider_rate: "161.600000" },
  },
  scenarios: [
    {
      drop_pct: "5%",
      mid_rate: "168.000000",
      provider_rate: "169.680000",
      parent_pays_bdt_minor: 170930000,
      extra_bdt_minor: 8400000,
      extra_pct: "5.17",
      display: {
        parent_pays: "BDT 1,709,300.00",
        extra: "BDT 84,000.00",
        extra_pct: "5.17%",
        provider_rate: "169.680000",
      },
    },
    {
      drop_pct: "10%",
      mid_rate: "176.000000",
      provider_rate: "177.760000",
      parent_pays_bdt_minor: 179330000,
      extra_bdt_minor: 16800000,
      extra_pct: "10.34",
      display: {
        parent_pays: "BDT 1,793,300.00",
        extra: "BDT 168,000.00",
        extra_pct: "10.34%",
        provider_rate: "177.760000",
      },
    },
  ],
  assumption:
    "The taka weakens so that each GBP costs the given percentage more taka; fixed fees in taka stay as they are.",
  synthetic: true,
  note: "A what-if on synthetic rates, not a forecast. Indicative. Confirm with your AD bank.",
};

import type { PlanView } from "@/lib/api/types";

/** The deadline planner's answer for a due date of 30 Oct 2026 (the engine's own dates). */
export const PLAN_VIEW: PlanView = {
  due_date: "2026-10-30",
  latest_send_date: "2026-10-22",
  recommended_send_date: "2026-10-21",
  earliest_send_date: "2026-10-19",
  status: "ON_TRACK",
  days_until_latest_send: 6,
  settlement_business_days: 3,
  buffer_days: 2,
  bank_cutoff_local: "15:00",
  skipped_days: [],
  warnings: [],
  indicative: "Indicative. Confirm with your AD bank.",
  destination_country: "GB",
};
