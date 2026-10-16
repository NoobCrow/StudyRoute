import { TZDate } from "@date-fns/tz";
import { format } from "date-fns";

import type { PaymentBrief, PaymentState } from "@/lib/api/types";

// Lists, filters, counts and sorting over payments the API already sent. Nothing here adds money up or
// works an amount out: amounts are shown as the API formatted them, and the order of amounts is only
// used inside one currency.

export type PaymentStatus = "in_progress" | "completed" | "needs_attention" | "cancelled";
export type StatusFilter = "all" | Exclude<PaymentStatus, "cancelled">;
export type RangePreset = "7d" | "30d" | "year" | "all";
export type SortKey = "reference" | "recipient" | "amount" | "provider" | "status" | "created";
export type SortDir = "asc" | "desc";

export const STATUS_FILTERS: readonly StatusFilter[] = [
  "all",
  "in_progress",
  "completed",
  "needs_attention",
];

export const STATUS_LABEL: Record<PaymentStatus, string> = {
  in_progress: "In progress",
  completed: "Completed",
  needs_attention: "Needs attention",
  cancelled: "Cancelled",
};

const BY_STATE: Record<PaymentState, PaymentStatus> = {
  DRAFT: "in_progress",
  QUOTED: "in_progress",
  PENDING_APPROVAL: "in_progress",
  APPROVED: "in_progress",
  SUBMITTED: "in_progress",
  SETTLED: "completed",
  REJECTED: "needs_attention",
  FAILED: "needs_attention",
  CANCELLED: "cancelled",
};

/** The four words the list uses for the API's nine states. */
export function statusOf(state: PaymentState): PaymentStatus {
  return BY_STATE[state];
}

/** The states the server lets the parent cancel (see the state machine: before the money is submitted). */
const CANCELLABLE: readonly PaymentState[] = ["DRAFT", "QUOTED", "PENDING_APPROVAL", "APPROVED"];

export function canCancel(state: PaymentState): boolean {
  return CANCELLABLE.includes(state);
}

/** The Dhaka calendar day of an instant, as YYYY-MM-DD. Date ranges are inclusive on this clock. */
export function dhakaDay(iso: string): string {
  return format(new TZDate(iso, "Asia/Dhaka"), "yyyy-MM-dd");
}

export interface DayRange {
  from: string;
  to: string;
}

function shiftDay(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** The days a preset covers, ending today (Dhaka). "all" is no limit. */
export function rangeFor(preset: RangePreset, today: string): DayRange | null {
  if (preset === "7d") return { from: shiftDay(today, -6), to: today };
  if (preset === "30d") return { from: shiftDay(today, -29), to: today };
  if (preset === "year") return { from: `${today.slice(0, 4)}-01-01`, to: today };
  return null;
}

export interface PaymentFilters {
  status: StatusFilter;
  q: string;
  /** A currency code, or "" for every currency. */
  currency: string;
  range: DayRange | null;
}

function matchesStatus(payment: PaymentBrief, status: StatusFilter): boolean {
  return status === "all" || statusOf(payment.state) === status;
}

/** Everything but the status tab: the set the tab counts are taken from. */
export function filterExceptStatus(
  payments: readonly PaymentBrief[],
  filters: Omit<PaymentFilters, "status">,
): PaymentBrief[] {
  const needle = filters.q.trim().toLowerCase();
  return payments.filter((payment) => {
    if (filters.currency && payment.target.currency !== filters.currency) return false;
    if (filters.range) {
      const day = dhakaDay(payment.created_at);
      if (day < filters.range.from || day > filters.range.to) return false;
    }
    if (!needle) return true;
    return (
      payment.reference.toLowerCase().includes(needle) ||
      payment.recipient_label.toLowerCase().includes(needle)
    );
  });
}

export function filterPayments(
  payments: readonly PaymentBrief[],
  filters: PaymentFilters,
): PaymentBrief[] {
  return filterExceptStatus(payments, filters).filter((p) => matchesStatus(p, filters.status));
}

export type StatusCounts = Record<StatusFilter, number>;

export function statusCounts(payments: readonly PaymentBrief[]): StatusCounts {
  const counts: StatusCounts = {
    all: payments.length,
    in_progress: 0,
    completed: 0,
    needs_attention: 0,
  };
  for (const payment of payments) {
    const status = statusOf(payment.state);
    if (status !== "cancelled") counts[status] += 1;
  }
  return counts;
}

/** The currencies present in a list, for the currency filter. */
export function currenciesOf(payments: readonly PaymentBrief[]): string[] {
  return [...new Set(payments.map((p) => p.target.currency))].sort();
}

const text = (a: string, b: string) => a.localeCompare(b, "en", { sensitivity: "base" });

/** Sorts a copy. Amounts are compared as the integers the API sent, grouped by currency first. */
export function sortPayments(
  payments: readonly PaymentBrief[],
  key: SortKey,
  dir: SortDir,
): PaymentBrief[] {
  const compare = (a: PaymentBrief, b: PaymentBrief): number => {
    switch (key) {
      case "reference":
        return text(a.reference, b.reference);
      case "recipient":
        return text(a.recipient_label, b.recipient_label);
      case "provider":
        return text(a.provider_name, b.provider_name);
      case "status":
        return text(STATUS_LABEL[statusOf(a.state)], STATUS_LABEL[statusOf(b.state)]);
      case "amount":
        return (
          text(a.target.currency, b.target.currency) ||
          a.target.amount_minor - b.target.amount_minor
        );
      case "created":
        return a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0;
    }
  };
  const sign = dir === "asc" ? 1 : -1;
  // The id breaks ties, so the order never jumps between renders.
  return [...payments].sort((a, b) => sign * compare(a, b) || text(a.payment_id, b.payment_id));
}

export interface PageSlice<T> {
  items: T[];
  /** The page actually shown (1-based), after clamping. */
  page: number;
  pages: number;
  total: number;
}

export function paginate<T>(items: readonly T[], page: number, size: number): PageSlice<T> {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(1, Math.trunc(page) || 1), pages);
  return {
    items: items.slice((current - 1) * size, current * size),
    page: current,
    pages,
    total: items.length,
  };
}

/** A spreadsheet treats a cell that starts with one of these as a formula, so such cells get a quote mark. */
function csvCell(value: string): string {
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** The rows on screen as CSV: only what the person can already see, formatted as the API sent it. */
export function paymentsToCsv(payments: readonly PaymentBrief[]): string {
  const rows = payments.map((p) => [
    p.reference,
    p.recipient_label,
    p.target.formatted,
    p.provider_name,
    STATUS_LABEL[statusOf(p.state)],
    p.created_at,
  ]);
  const head = ["Reference", "Recipient", "Beneficiary receives", "Provider", "Status", "Created"];
  return [head, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

/**
 * The page buttons to show: every page when there are few, otherwise the first, the last and the pages
 * around the current one, with "gap" where pages are left out.
 */
export function pageNumbers(page: number, pages: number): (number | "gap")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const wanted = new Set([1, pages, page - 1, page, page + 1]);
  const shown = [...wanted].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const out: (number | "gap")[] = [];
  shown.forEach((n, index) => {
    const before = shown[index - 1];
    if (before !== undefined && n - before > 1) out.push("gap");
    out.push(n);
  });
  return out;
}
