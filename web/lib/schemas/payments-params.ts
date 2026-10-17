import { z } from "zod";

import {
  STATUS_FILTERS,
  rangeFor,
  type DayRange,
  type RangePreset,
  type SortDir,
  type SortKey,
  type StatusFilter,
} from "@/lib/domain/payments";
import { isIsoDate } from "@/lib/schemas/compare";

// The address of the payments list: status, q, currency, range, page, and how it is sorted. Each one is
// checked on its own; a bad one falls back to its default, so a mistyped link still opens the list.

export interface PaymentsParams {
  status: StatusFilter;
  q: string;
  /** A currency code, or "" for every currency. */
  currency: string;
  /** "7d", "30d", "year", "all", or two days joined by two dots: "2026-10-01..2026-10-16". */
  range: string;
  page: number;
  sort: SortKey;
  dir: SortDir;
}

export const DEFAULT_PAYMENTS_PARAMS: PaymentsParams = {
  status: "all",
  q: "",
  currency: "",
  range: "30d",
  page: 1,
  sort: "created",
  dir: "desc",
};

const SORT_KEYS = ["reference", "recipient", "amount", "provider", "status", "created"] as const;

const fields = {
  status: z.enum(STATUS_FILTERS as [StatusFilter, ...StatusFilter[]]),
  q: z.string().max(80),
  currency: z.string().regex(/^[A-Z]{3}$/),
  range: z.string().refine((value) => parseRange(value, "2000-01-01") !== undefined),
  page: z.coerce.number().int().min(1).max(10_000),
  sort: z.enum(SORT_KEYS),
  dir: z.enum(["asc", "desc"]),
};

const PRESETS: readonly string[] = ["7d", "30d", "year", "all"];

/**
 * The days a `range` value means. `null` is "no limit" (the "all" preset) and `undefined` is "this is
 * not a range": a preset needs `today` (Dhaka), a custom range carries its own days.
 */
export function parseRange(value: string, today: string): DayRange | null | undefined {
  if (PRESETS.includes(value)) return rangeFor(value as RangePreset, today);
  const match = /^([0-9]{4}-[0-9]{2}-[0-9]{2})\.\.([0-9]{4}-[0-9]{2}-[0-9]{2})$/.exec(value);
  if (!match) return undefined;
  const [, from = "", to = ""] = match;
  return isIsoDate(from) && isIsoDate(to) && from <= to ? { from, to } : undefined;
}

export function rangeValue(range: DayRange): string {
  return `${range.from}..${range.to}`;
}

export function readPaymentsParams(search: URLSearchParams): PaymentsParams {
  const take = <K extends keyof typeof fields>(key: K, fold: (v: string) => string = (v) => v) => {
    const raw = search.get(key);
    const parsed = raw === null ? null : fields[key].safeParse(fold(raw));
    return parsed?.success ? (parsed.data as z.infer<(typeof fields)[K]>) : null;
  };
  const d = DEFAULT_PAYMENTS_PARAMS;
  return {
    status: take("status", (v) => v.toLowerCase()) ?? d.status,
    q: take("q", (v) => v.trim()) ?? d.q,
    currency: take("currency", (v) => v.trim().toUpperCase()) ?? d.currency,
    range: take("range", (v) => v.trim().toLowerCase()) ?? d.range,
    page: take("page") ?? d.page,
    sort: take("sort", (v) => v.toLowerCase()) ?? d.sort,
    dir: take("dir", (v) => v.toLowerCase()) ?? d.dir,
  };
}

/** The search string for a view. Only what differs from the defaults is written, so the plain list has no query. */
export function writePaymentsParams(values: PaymentsParams): string {
  const params = new URLSearchParams();
  const d = DEFAULT_PAYMENTS_PARAMS;
  if (values.status !== d.status) params.set("status", values.status);
  if (values.q.trim() !== "") params.set("q", values.q.trim().slice(0, 80));
  if (values.currency !== d.currency) params.set("currency", values.currency);
  if (values.range !== d.range) params.set("range", values.range);
  if (values.page !== d.page) params.set("page", String(values.page));
  if (values.sort !== d.sort) params.set("sort", values.sort);
  if (values.dir !== d.dir) params.set("dir", values.dir);
  return params.toString();
}
