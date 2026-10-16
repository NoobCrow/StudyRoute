// A small stand-in for the StudyRoute API, so the smoke test needs no backend. Every answer here is
// synthetic. Anything this file does not know is refused loudly, which fails the test.
import type { Page, Route } from "@playwright/test";

const PERMISSIONS = [
  "quotes:create",
  "quotes:read",
  "payments:read",
  "payments:draft",
  "planner:read",
  "data:reset",
  "recipients:allowlist",
];

export const USER = {
  user_id: "usr_parent",
  email: "parent@demo.studyroute.test",
  display_name: "Demo Parent",
  role: "parent",
  kyc_status: "VERIFIED",
  payer: null,
  permissions: PERMISSIONS,
};

const TOKENS = {
  access_token: "acc_1",
  refresh_token: "ref_1",
  token_type: "bearer",
  expires_in: 900,
};

const CORRIDORS = {
  items: [
    {
      country: "GB",
      name: "United Kingdom",
      currency: "GBP",
      account_scheme: "IBAN_OR_UK_DOMESTIC",
      host_rail: "UK Faster Payments",
      mid_rate: "160",
      exponent: 2,
      featured: true,
      restricted: false,
      sample_amount: "10000",
    },
  ],
  providers: [],
};

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

function result(rank: number, id: string, name: string, shortfallMinor: number) {
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

const QUOTE = {
  quote_id: "qte_1",
  created_at: "2026-10-14T09:30:00Z",
  expires_at: "2099-01-01T00:00:00Z",
  status: "ACTIVE",
  seconds_left: 300,
  target: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
  purpose: "TUITION",
  destination_country: "GB",
  charge_code: "OUR",
  due_date: null,
  recipient_id: null,
  mid_rate: {
    value: "160.000000",
    source: "synthetic",
    as_of: "2026-10-14T09:29:50Z",
    display: "BDT 160.000000 per 1 GBP",
  },
  results: [
    result(1, "prov_b", "Provider B (synthetic)", 0),
    result(2, "prov_c", "Provider C (synthetic)", 3500),
  ],
  input_hash: "sha256:abc",
  synthetic: true,
  disclaimer: "Sandbox.",
  deadline_fit: null,
};

const STRESS = {
  quote_id: "qte_1",
  provider_id: "prov_b",
  provider_name: "Provider B (synthetic)",
  target: QUOTE.target,
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
  ],
  assumption: "The taka weakens so that each GBP costs the given percentage more taka.",
  synthetic: true,
  note: "A what-if on synthetic rates, not a forecast. Indicative. Confirm with your AD bank.",
};

const KYC = {
  user_id: "usr_parent",
  status: "VERIFIED",
  message: "Verified (simulated).",
  simulated: true,
  required_documents: [],
  provided_documents: [],
  missing: [],
  submitted_at: null,
  review_due_at: null,
};

const PLAN = {
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
  indicative: "Indicative. Confirm with your AD bank.",
  destination_country: "GB",
};

const RUNWAY = {
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
    note: "Not an official figure.",
  },
};

const RATES = {
  currency: "GBP",
  source: "synthetic",
  disclaimer: "Synthetic data. Not a forecast. Indicative. Confirm with your AD bank.",
  points: [
    { date: "2026-10-12", rate: "159.500000" },
    { date: "2026-10-13", rate: "160.500000" },
    { date: "2026-10-14", rate: "161.000000" },
  ],
  hint: {
    kind: "NEUTRAL",
    today: "161.000000",
    average: "160.333333",
    gap_pct: "0.42",
    days: 3,
    message: "Today is close to the average.",
  },
};

const SEND_PLAN = {
  total: { amount_minor: 1200000, currency: "GBP", formatted: "GBP 12,000.00" },
  months: 12,
  cheapest_key: "upfront",
  options: [],
  synthetic: true,
  disclaimer: "Synthetic rates and fees. Indicative. Confirm with your AD bank.",
  trade_off: "Sending less often costs less in fixed fees, but moves money before it is needed.",
};

const HEALTH = {
  status: "ok",
  mode: "sandbox",
  ai_mode: "template",
  demo: {
    accounts: ["parent@demo.studyroute.test"],
    password: "Sandbox#2026",
    mfa_code: "246810",
    parent_id: "usr_parent",
  },
};

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function problem(route: Route, status: number, code: string, detail: string): Promise<void> {
  return json(
    route,
    { type: "about:blank", title: code, status, code, detail, request_id: "req_e2e" },
    status,
  );
}

/** Answers every /api/v1 call the dashboard, sign-in and compare screens make. */
export async function mockApi(page: Page): Promise<void> {
  let allowlisted = false;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    if (path === "/health") return json(route, HEALTH);
    if (path === "/auth/login") {
      const body = request.postDataJSON() as { password?: string };
      return body.password === HEALTH.demo.password
        ? json(route, { ...TOKENS, user: USER })
        : problem(route, 401, "INVALID_CREDENTIALS", "Email or password is wrong.");
    }
    if (path === "/auth/refresh") return json(route, TOKENS);
    if (path === "/auth/logout") return json(route, { ok: true });
    if (path === "/me") return json(route, USER);
    if (path === "/corridors") return json(route, CORRIDORS);
    if (path === "/kyc/status") return json(route, KYC);
    if (path === "/payments") return json(route, { items: [], next_cursor: null });
    if (path === "/recipients") {
      return json(route, {
        items: [
          {
            recipient_id: "rcp_1",
            type: "UNIVERSITY",
            display_name: "University of Example (synthetic)",
            country: "GB",
            bic: "EXMPGB2L",
            account_kind: "IBAN",
            account_masked: "GB** **** 4821",
            routing_code: null,
            label: "University of Example (synthetic) GB** **** 4821",
            allowlisted,
            allowlisted_at: null,
            created_at: "2026-10-14T12:52:00Z",
          },
        ],
      });
    }
    if (path === "/recipients/rcp_1" && method === "PATCH") {
      allowlisted = (request.postDataJSON() as { allowlisted: boolean }).allowlisted;
      return json(route, { recipient_id: "rcp_1", allowlisted });
    }
    if (path === "/auth/mfa/verify") return json(route, { mfa_proof: "proof_e2e" });
    if (path === "/planner/deadline") return json(route, PLAN);
    if (path === "/planner/runway") return json(route, RUNWAY);
    if (path === "/planner/send-plan") return json(route, SEND_PLAN);
    if (path === "/rates/history") return json(route, RATES);
    if (path === "/quotes" && method === "POST") return json(route, QUOTE, 201);
    if (path === "/quotes/qte_1/stress") return json(route, STRESS);
    return problem(route, 500, "NOT_MOCKED", `${method} ${path} is not mocked.`);
  });
}
