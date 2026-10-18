import { z } from "zod";

import type { Housing } from "@/lib/api/types";

// The address of the student guide: which tab, and what the budget finder is asked. Each value is
// checked on its own; a bad one falls back to its default, so a mistyped link still opens the page.

export type GuideTab = "budget" | "arrival";

export interface GuideParams {
  tab: GuideTab;
  /** The monthly budget in taka as typed (digits and one optional decimal point), or "" for none. */
  budget: string;
  housing: Housing;
  /** The budget finder's country, or "" for every country. */
  country: string;
  /** The arrival guide's country. */
  arrival: string;
}

export const DEFAULT_GUIDE_PARAMS: GuideParams = {
  tab: "budget",
  budget: "200000",
  housing: "shared",
  country: "",
  arrival: "GB",
};

const fields = {
  tab: z.enum(["budget", "arrival"]),
  budget: z.string().regex(/^(?:[0-9]{1,9}(?:[.][0-9]{1,2})?)?$/),
  housing: z.enum(["shared", "studio"]),
  country: z.string().regex(/^(?:[A-Z]{2})?$/),
  arrival: z.string().regex(/^[A-Z]{2}$/),
};

export function readGuideParams(search: URLSearchParams): GuideParams {
  const take = <K extends keyof typeof fields>(key: K, fold: (v: string) => string = (v) => v) => {
    const raw = search.get(key);
    const parsed = raw === null ? null : fields[key].safeParse(fold(raw));
    return parsed?.success ? (parsed.data as z.infer<(typeof fields)[K]>) : null;
  };
  const d = DEFAULT_GUIDE_PARAMS;
  const plain = (v: string) => v.trim().replace(/,/g, "");
  return {
    tab: take("tab", (v) => v.toLowerCase()) ?? d.tab,
    budget: take("budget", plain) ?? d.budget,
    housing: take("housing", (v) => v.toLowerCase()) ?? d.housing,
    country: take("country", (v) => v.trim().toUpperCase()) ?? d.country,
    arrival: take("arrival", (v) => v.trim().toUpperCase()) ?? d.arrival,
  };
}

/** The search string for a view. Only what differs from the defaults is written; an empty budget is written as `budget=`. */
export function writeGuideParams(values: GuideParams): string {
  const params = new URLSearchParams();
  const d = DEFAULT_GUIDE_PARAMS;
  if (values.tab !== d.tab) params.set("tab", values.tab);
  if (values.budget !== d.budget) params.set("budget", values.budget);
  if (values.housing !== d.housing) params.set("housing", values.housing);
  if (values.country !== d.country) params.set("country", values.country);
  if (values.arrival !== d.arrival) params.set("arrival", values.arrival);
  return params.toString();
}
