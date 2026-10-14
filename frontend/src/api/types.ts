// Shapes returned by the StudyRoute sandbox API. Money is always {amount_minor, currency}
// plus a "formatted" string made by the backend: the UI never calculates or formats money.

export type Role = "parent" | "student" | "admin";
export type KycStatusName = "VERIFIED" | "PENDING" | "NEEDS_DOCUMENTS";
export type ChargeCode = "OUR" | "SHA" | "BEN";
export type PaymentState =
  | "DRAFT" | "QUOTED" | "PENDING_APPROVAL" | "APPROVED"
  | "SUBMITTED" | "SETTLED" | "REJECTED" | "CANCELLED" | "FAILED";

export interface Money { amount_minor: number; currency: string; formatted: string }
export interface Warning { code: string; message: string }

export interface Problem {
  type: string; title: string; status: number; code: string; detail: string; request_id: string;
  [extra: string]: unknown;
}

export interface UserView {
  user_id: string; email: string; display_name: string; role: Role;
  kyc_status: KycStatusName | null;
  payer: { user_id: string; display_name: string } | null;
  permissions: string[];
}
export interface LoginResponse {
  access_token: string; refresh_token: string; expires_in: number; expires_at: string; user: UserView;
}
export interface RefreshResponse { access_token: string; refresh_token: string; expires_in: number }

export interface Health {
  status: string; app: string; version: string; mode: string; banner: string; ai_mode: string;
  demo?: { accounts: string[]; password: string; mfa_code: string; parent_id: string };
}

export interface QuoteResult {
  rank: number; provider_id: string; provider_name: string; provider_rate: string; margin_pct: string;
  charge_code: ChargeCode; requested_charge_code: ChargeCode;
  fees: {
    fixed_bdt_minor: number; swift_bdt_minor: number;
    intermediary_foreign_minor: number; receiving_foreign_minor: number;
  };
  shortfall_foreign_minor: number; total_cost_bdt_minor: number; cost_pct: string;
  parent_pays_bdt_minor: number; eta_business_days: number; warnings: Warning[];
  display: Record<
    | "provider_rate" | "margin_pct" | "cost_pct" | "fx_cost" | "fixed_fee" | "swift_fee"
    | "sender_extra" | "shortfall_bdt" | "total_cost" | "parent_pays" | "intermediary_fee"
    | "receiving_fee" | "shortfall" | "beneficiary_receives",
    string
  >;
}
export interface Quote {
  quote_id: string; created_at: string; expires_at: string; status: "ACTIVE" | "EXPIRED";
  seconds_left: number; target: Money; purpose: string; destination_country: string;
  charge_code: ChargeCode; due_date: string | null; recipient_id: string | null;
  mid_rate: { value: string; source: string; as_of: string; display: string };
  results: QuoteResult[]; input_hash: string; synthetic: boolean; disclaimer: string;
}

export interface Recipient {
  recipient_id: string; type: "UNIVERSITY" | "STUDENT"; display_name: string; country: string;
  bic: string; account_kind: string; account_masked: string; routing_code: string | null;
  label: string; allowlisted: boolean; allowlisted_at: string | null; created_at: string;
}

export interface Blocker { code: string; message: string }
export interface Summary {
  payment_id: string; recipient: string; provider_name: string; reference: string;
  beneficiary_receives: { amount_minor: number; currency: string };
  rate: string; charge_code: ChargeCode; total_cost_bdt_minor: number; parent_pays_bdt_minor: number;
  latest_send_date: string | null; quote_expires_at: string; disclaimer: string;
  display: { beneficiary_receives: string; total_cost: string; parent_pays: string; cost_pct: string };
  shortfall_foreign_minor: number;
}
export interface PaymentBrief {
  payment_id: string; state: PaymentState; target: Money; provider_id: string; provider_name: string;
  recipient_label: string; reference: string; due_date: string | null; uetr: string | null;
  parent_pays: string; created_at: string; updated_at: string;
}
export interface Payment extends PaymentBrief {
  quote_id: string; quote_expires_at: string; quote_status: "ACTIVE" | "EXPIRED";
  destination_country: string; purpose: string;
  recipient: { recipient_id: string; label: string; allowlisted: boolean };
  result: QuoteResult; latest_send_date: string | null;
  summary: Summary | null; summary_hash: string | null; summary_preview: Summary | null;
  approved_by: string | null; approved_at: string | null;
  submitted_at: string | null; settled_at: string | null;
  failure_reason: string | null;
  readiness: { blockers: Blocker[]; can_request_approval: boolean; can_approve: boolean };
  simulated: true; disclaimer: string;
}
export interface ApprovalRequested {
  payment_id: string; state: PaymentState; summary: Summary; summary_hash: string;
}
export interface Tracker {
  payment_id: string; uetr: string | null; state: PaymentState; host_rail: string; simulated: true;
  timeline: { state: PaymentState; at: string; note: string | null; actor_type: string }[];
}
export interface Mt103Preview {
  format: string; simulated: true; notes: string[];
  fields: { tag: string; name: string; value: string; note: string }[];
  pacs008: { ChrgBr: string; UETR: string | null; RmtInf: string };
}

export interface KycView {
  user_id: string; status: KycStatusName; message: string; simulated: true;
  required_documents: { key: string; label: string }[]; provided_documents: string[];
  missing: string[]; submitted_at: string | null; review_due_at: string | null;
}
export interface PlanView {
  due_date: string; latest_send_date: string; recommended_send_date: string;
  earliest_send_date: string; status: "ON_TRACK" | "TIGHT" | "AT_RISK" | "LATE";
  days_until_latest_send: number; settlement_business_days: number; buffer_days: number;
  bank_cutoff_local: string; skipped_days: { date: string; reasons: string[] }[];
  warnings: Warning[]; indicative: string; destination_country: string;
}
export interface ChecklistItem { key: string; label: string; hint: string; provided: boolean }
export interface Checklist {
  country: string; purpose: string; items: ChecklistItem[]; verified: boolean;
  source_url: string | null; last_checked: string | null; note: string | null; indicative: string;
}
export interface DocumentView {
  document_id: string; kind: string; filename: string; payment_id: string | null;
  size_bytes: number; has_content: boolean; content_preview: string; created_at: string; mock: true;
}
export interface RuleView {
  key: string; value: unknown; source_url: string | null; last_checked: string | null;
  verified: boolean; kind: string; note: string | null; updated_by: string;
  updated_at: string | null; badge: "NOT_VERIFIED" | null; indicative: string | null;
}
export interface AuditEventView {
  event_id: string; seq: number; timestamp: string; actor_type: string; actor_id: string;
  action: string; payment_id: string | null; quote_id: string | null; amount_minor: number | null;
  currency: string | null; amount_display?: string; recipient_id: string | null;
  decision: string | null; reason_code: string | null; detail: string | null;
  input_hash: string | null; output_hash: string | null; model_version: string | null;
  prev_event_hash: string; this_event_hash: string;
}
export interface VerifyView {
  status: "PASS" | "FAIL"; events_checked: number; failed_seq: number | null;
  reason: string | null; head: { seq: number; hash: string };
}
export interface CorridorList { items: Corridor[]; providers: string[] }
export interface Corridor {
  country: string; name: string; currency: string; account_scheme: string;
  host_rail: string; mid_rate: string;
}
export interface ChatAction {
  tool: "create_draft" | "request_approval"; args: Record<string, string>;
  requires_human: true; missing: string[];
}
export interface ChatResponse {
  reply: string; facts_used: string[]; facts: { id: string; label: string; value: string }[];
  guard: { status: string; flags: string[]; failure: string | null; retries: number };
  proposed_actions: ChatAction[]; task: TaskCard | null; mode: "template" | "llm"; model_version: string;
  disclaimer: string; debug: { masked_prompt: string; note: string };
}
export interface RunwayView {
  display: { amount: string; monthly_cost: string; covers: string; full_months: string; leftover: string };
  monthly_cost_usd_equivalent: string;
  reference: { label: string; value: string; verified: boolean; badge: string | null; note: string };
}
export interface RateHistory {
  currency: string; source: string; disclaimer: string;
  points: { date: string; rate: string }[];
  hint: {
    kind: "SEND_NOW" | "WAIT_MAY_HELP" | "NEUTRAL"; today: string; average: string;
    gap_pct: string; days: number; message: string;
  };
}

export interface Page<T> { items: T[]; next_cursor: string | number | null }

export interface SandboxInfo {
  sandbox: true; banner: string; disclaimer: string; ai_mode: "template" | "llm";
  simulated: { component: string; what: string }[];
  scenarios: { token: string; where: string; effect: string }[];
  providers: { provider_id: string; name: string }[];
  timings: {
    quote_ttl_seconds: number; mfa_proof_ttl_seconds: number; kyc_review_seconds: number;
    submit_delay_seconds: number; settle_delay_seconds: number; slow_settle_delay_seconds: number;
  };
  limits: { per_transaction_usd_equivalent: number; daily_usd_equivalent: number; indicative: string };
  demo: { password: string; mfa_code: string } | null;
}

export interface PlanStep { key: string; label: string; state: "done" | "todo"; detail: string; link: string | null }
export interface PlanProvider {
  provider_id: string; provider_name: string; cost_pct: string; parent_pays: string; total_cost: string;
  shortfall: string; has_shortfall: boolean; charge_code: ChargeCode; eta_business_days: number;
}
export interface PaymentPlanCard {
  kind: "payment_plan"; status: "ready";
  request: { amount: Money; purpose: string; country: string; country_name: string; due_date: string | null; charge_code: ChargeCode };
  quote: { quote_id: string; expires_at: string };
  best: PlanProvider; alternatives: PlanProvider[];
  deadline: { due_date: string; latest_send_date: string; recommended_send_date: string; status: PlanView["status"] } | null;
  recipients: { recipient_id: string; label: string; allowlisted: boolean }[];
  steps: PlanStep[];
  draft: { quote_id: string; provider_id: string; recipient_id: string | null; missing: string[] };
}
export interface CadenceOptionView {
  key: string; label: string; transfers: number; provider_id: string; provider_name: string;
  charge_code: ChargeCode; shortfall_foreign_minor: number; exceeds_sandbox_cap: boolean;
  display: { per_transfer: string; total_cost: string; parent_pays: string; avg_cost_pct: string; saving_vs_monthly: string };
}
export interface SendPlan {
  total: Money; months: number; cheapest_key: string; options: CadenceOptionView[];
  synthetic: true; disclaimer: string; trade_off: string;
}
export interface SendPlanCardData { kind: "send_plan"; status: "ready"; plan: SendPlan }
export interface TaskGap { kind: "payment_plan" | "send_plan"; status: "needs_input" | "error"; missing?: string[]; message?: string }
export type TaskCard = PaymentPlanCard | SendPlanCardData | TaskGap;

export type ControlResult = "PASS" | "PENDING" | "NOT_YET" | "BLOCKED" | "FAIL";
export interface ComplianceReport {
  report_type: string; generated_at: string; synthetic: true; disclaimer: string; report_hash: string;
  payment: {
    payment_id: string; state: PaymentState; reference: string; provider_name: string; uetr: string | null;
    due_date: string | null; latest_send_date: string | null; created_at: string; approved_at: string | null;
    submitted_at: string | null; settled_at: string | null; failure_reason: string | null;
  };
  amount: { beneficiary_receives: string; rate: string; charge_code: ChargeCode; total_cost: string; cost_pct: string; parent_pays: string; shortfall: string };
  parties: {
    originator: { name: string; address: string; country: string };
    beneficiary: { name: string; account_masked: string; bic: string; country: string };
  };
  approval: { approved: boolean; approved_by: string | null; approved_at: string | null; summary_hash: string | null; mfa_proof_reference: string | null };
  controls: { key: string; label: string; result: ControlResult; evidence: string }[];
  timeline: Tracker["timeline"];
  audit: { events: AuditEventView[]; chain: VerifyView };
}

// --- sandbox bank network (all simulated) -----------------------------------------------------
export type BankStatus =
  | "PENDING_CONFIRMATION" | "ACCEPTED" | "IN_TRANSIT" | "SETTLED" | "RETURNED" | "CANCELLED";

export interface BankAccountView {
  id: string; bank_code: string; bank_name: string; country: string | null; kind: string;
  number: string; holder: string; label: string; currency: string; balance: Money;
  household: boolean; simulated: true;
}
export type Beneficiary = Omit<BankAccountView, "balance">;
export interface BankTotals {
  by_currency: { currency: string; accounts: number; balance: Money; bdt_equivalent: Money }[];
  bdt_total: Money; note: string;
}

export interface BankStep {
  stage: string; bank: string; bank_name: string; summary: string; delay_seconds: number;
  done: boolean; message: string;
}
export interface BankEvent {
  at: string; stage: string; bank_code: string; bank_name: string; event: string; note: string;
  message: { type?: string; fields?: { tag: string; name: string; value: string }[] } | null;
}
export interface BankJournalLine { side: "DEBIT" | "CREDIT"; bank: string; account: string; amount: Money }
export interface BankJournal {
  id: string; kind: string; stage: string; memo: string; posted_at: string; lines: BankJournalLine[];
}
export interface BankTransfer {
  id: string; status: BankStatus; kind: "NATIONAL" | "INTERNATIONAL"; rail: string; reference: string;
  uetr: string | null; source: BankAccountView; destination: Beneficiary;
  debit: Money; credit: Money; fee: Money; figures: Record<string, unknown>; plan_hash: string;
  steps: BankStep[]; next_step_at: string | null; failure_reason: string | null;
  created_at: string; confirmed_at: string | null; settled_at: string | null;
  blockers: Warning[]; simulated: true; note: string;
  events?: BankEvent[]; journals?: BankJournal[];
}
export interface BankRail {
  code: string; label: string; fee_fixed_minor: number; fee_bps: number;
  min_minor: number; max_minor: number | null; seconds: number;
}
export interface BankMirror {
  kind: string; holder_bank_name: string; other_name: string; currency: string;
  balance: Money; reconciled: boolean;
}
export interface BankNetwork {
  ready: boolean; simulated: true; all_ok?: boolean;
  directory?: { rails: Record<string, BankRail[]>; banks: { code: string; name: string; role: string }[]; note: string };
  trial_balance?: Record<string, { debits: number; credits: number; balanced: boolean }>;
  mirror_accounts?: BankMirror[];
  accounts_not_matching_entries?: number;
}

