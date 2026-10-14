// Helpers for the destination list. Every country is a destination; six are hand-written
// ("featured") and listed first. This is only about how the list is shown and what the forms
// start with. Every number that matters still comes from the backend.

import type { Corridor } from "../api/types";

export const POPULAR_LABEL = "Popular study destinations";
export const ALL_LABEL = "All countries";

const byName = (a: Corridor, b: Corridor) => a.name.localeCompare(b.name);

export function splitCorridors(items: Corridor[]): { featured: Corridor[]; others: Corridor[] } {
  return {
    featured: items.filter((c) => c.featured).sort(byName),
    others: items.filter((c) => !c.featured).sort(byName),
  };
}

/** Currencies for a select: the featured corridors' currencies first, then the rest by code. */
export function currencyGroups(items: Corridor[]): { featured: string[]; others: string[] } {
  const featured = [...new Set(items.filter((c) => c.featured).map((c) => c.currency))].sort();
  const others = [...new Set(items.filter((c) => !c.featured).map((c) => c.currency))]
    .filter((code) => !featured.includes(code))
    .sort();
  return { featured, others };
}

/** The corridor to read a currency's decimals and sample amount from (many countries can share one). */
export function corridorForCurrency(items: Corridor[], currency: string): Corridor | undefined {
  const matches = items.filter((c) => c.currency === currency);
  return matches.find((c) => c.featured && !c.restricted) ?? matches.find((c) => !c.restricted) ?? matches[0];
}

export function exponentFor(items: Corridor[], currency: string): number {
  return corridorForCurrency(items, currency)?.exponent ?? 2;
}

export interface FormDefaults {
  /** The amount for a quote, and "amount sent" on the runway card. */
  amount: string;
  runwayAmount: string;
  runwayMonthly: string;
  sendPlanMonthly: string;
}

const whole = (value: number) => String(Math.max(1, Math.round(value)));

/** Starting values for the money forms, in proportion to the sample amount (GBP: 10000, 5000, 1200, 1000). */
export function formDefaults(corridor: Corridor | undefined): FormDefaults {
  const sample = Number(corridor?.sample_amount ?? "10000");
  const base = Number.isFinite(sample) && sample > 0 ? sample : 10000;
  return {
    amount: whole(base),
    runwayAmount: whole(base / 2),
    runwayMonthly: whole(base * 0.12),
    sendPlanMonthly: whole(base / 10),
  };
}
