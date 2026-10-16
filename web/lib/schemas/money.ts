import { z } from "zod";

import { parseMajorToMinor } from "@/lib/money";

/**
 * A money field typed as text ("10,000.50"). It is checked against the currency's decimals and, when
 * valid, kept as the text the person typed: the API receives integer minor units built by
 * parseMajorToMinor at submit time. No floating point is involved.
 */
export function moneyText(label: string, exponent: () => number) {
  return z.string().superRefine((value, ctx) => {
    const parsed = parseMajorToMinor(value, exponent());
    if (!parsed.ok) ctx.addIssue({ code: "custom", message: `${label}: ${parsed.error}` });
  });
}

export const wholeMonths = z.string().superRefine((value, ctx) => {
  const count = Number(value);
  if (!/^[0-9]+$/.test(value.trim()) || !Number.isInteger(count) || count < 1 || count > 60) {
    ctx.addIssue({ code: "custom", message: "Months: enter a whole number from 1 to 60." });
  }
});

export const chargeCodes = ["OUR", "SHA", "BEN"] as const;
