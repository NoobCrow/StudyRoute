import { z } from "zod";

import { parseMajorToMinor } from "@/lib/money";
import { chargeCodes, moneyText } from "@/lib/schemas/money";

export const PURPOSES = ["TUITION", "LIVING"] as const;

export interface CompareValues {
  country: string;
  amount: string;
  purpose: (typeof PURPOSES)[number];
  charge: (typeof chargeCodes)[number];
  dueDate: string;
  recipientId: string;
}

/** True for a real calendar day written as YYYY-MM-DD. */
export function isIsoDate(value: string): boolean {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

/**
 * The request form. `exponent` is the currency's decimals (2 for GBP, 0 for JPY) and `today` the first
 * day a due date may have (ISO, the Dhaka calendar day). The amount stays the text that was typed; the
 * API receives integer minor units built from it by parseMajorToMinor.
 */
export function quoteRequestSchema(exponent: number, today: string) {
  return z.object({
    country: z.string().regex(/^[A-Z]{2}$/, "Choose a destination country."),
    amount: moneyText("Amount", () => exponent),
    purpose: z.enum(PURPOSES),
    charge: z.enum(chargeCodes),
    dueDate: z
      .string()
      .min(1, "Choose the date the university needs the money.")
      .refine(isIsoDate, "Choose a valid date.")
      .refine((value) => value >= today, "The due date cannot be in the past."),
    recipientId: z.string().max(64),
  });
}

// --- the address of a comparison: destination, amount, purpose, chargeCode, dueDate, recipientId ------

const paramSchemas = {
  destination: z.string().regex(/^[A-Z]{2}$/),
  amount: z.string().regex(/^[0-9]{1,12}([.][0-9]{1,6})?$/),
  purpose: z.enum(PURPOSES),
  chargeCode: z.enum(chargeCodes),
  dueDate: z.string().refine(isIsoDate),
  recipientId: z.string().regex(/^[A-Za-z0-9_-]{1,64}$/),
} as const;

/**
 * Reads a comparison from a URL's search parameters. Every parameter is checked on its own: a bad or
 * missing one falls back to `defaults`, so a mistyped link still opens a working form.
 */
export function readCompareParams(search: URLSearchParams, defaults: CompareValues): CompareValues {
  const pick = <K extends keyof typeof paramSchemas>(key: K, fold: (v: string) => string) => {
    const raw = search.get(key);
    const parsed = raw === null ? null : paramSchemas[key].safeParse(fold(raw));
    return parsed?.success ? (parsed.data as string) : null;
  };
  const upper = (v: string) => v.trim().toUpperCase();
  const keep = (v: string) => v.trim();
  return {
    country: pick("destination", upper) ?? defaults.country,
    amount: pick("amount", keep) ?? defaults.amount,
    purpose: (pick("purpose", upper) as CompareValues["purpose"] | null) ?? defaults.purpose,
    charge: (pick("chargeCode", upper) as CompareValues["charge"] | null) ?? defaults.charge,
    dueDate: pick("dueDate", keep) ?? defaults.dueDate,
    recipientId: pick("recipientId", keep) ?? defaults.recipientId,
  };
}

/** The search string for a comparison. Parts that are not valid are left out rather than written. */
export function writeCompareParams(values: CompareValues): string {
  const params = new URLSearchParams();
  const put = (key: keyof typeof paramSchemas, value: string) => {
    if (paramSchemas[key].safeParse(value).success) params.set(key, value);
  };
  put("destination", values.country);
  const amount = values.amount.replace(/[\s,]/g, "");
  put("amount", amount);
  put("purpose", values.purpose);
  put("chargeCode", values.charge);
  put("dueDate", values.dueDate);
  if (values.recipientId) put("recipientId", values.recipientId);
  return params.toString();
}

/** Minor units for a typed amount, or null when it is not valid for the currency. */
export function amountToMinor(amount: string, exponent: number): number | null {
  const parsed = parseMajorToMinor(amount, exponent);
  return parsed.ok ? parsed.minor : null;
}
