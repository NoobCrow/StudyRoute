import { z } from "zod";

import type { Corridor } from "@/lib/api/types";
import {
  normalizeIban,
  validateBic,
  validateIban,
  validateUkAccount,
} from "@/lib/domain/recipient-validation";

export const BIC_PATTERN = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;
export const EXAMPLE = {
  bic: "EXMPGB2L",
  iban: "GB08EXMP12345612344821",
  name: "University of Example (synthetic)",
};

export type UkMode = "iban" | "domestic";

export function usesIban(corridor: Corridor | undefined, ukMode: UkMode): boolean {
  if (!corridor) return true;
  return (
    corridor.account_scheme === "IBAN" ||
    (corridor.account_scheme === "IBAN_OR_UK_DOMESTIC" && ukMode === "iban")
  );
}

/**
 * The recipient form. Which account fields are required depends on the country's account scheme. The
 * checks (BIC country letters, IBAN check digits, UK sort code) are the same ones the server makes
 * again: they are here to say what is wrong before anything is sent.
 */
export function recipientSchema(corridor: Corridor | undefined, ukMode: UkMode) {
  const iban = usesIban(corridor, ukMode);
  const scheme = corridor?.account_scheme;
  return z
    .object({
      type: z.enum(["UNIVERSITY", "STUDENT"]),
      name: z
        .string()
        .trim()
        .min(1, "Enter the recipient's name.")
        .max(140, "The name can have at most 140 characters."),
      country: z.string().min(1),
      bic: z
        .string()
        .trim()
        .transform((value) => value.toUpperCase()),
      ukMode: z.enum(["iban", "domestic"]),
      iban: z.string(),
      account: z.string(),
      routing: z.string(),
    })
    .superRefine((values, ctx) => {
      const issue = (path: string, message: string) =>
        ctx.addIssue({ code: "custom", path: [path], message });
      const bic = validateBic(values.bic, values.country);
      if (!bic.ok) issue("bic", bic.message);
      if (iban) {
        if (!values.iban.trim()) issue("iban", "Enter the IBAN.");
        else {
          const checked = validateIban(values.iban, values.country);
          if (!checked.ok) issue("iban", checked.message);
        }
      } else if (scheme === "IBAN_OR_UK_DOMESTIC") {
        const uk = validateUkAccount(values.routing, values.account, values.country);
        if (!values.routing.trim()) issue("routing", "Enter the sort code.");
        else if (uk.errors.sortCode) issue("routing", uk.errors.sortCode);
        if (!values.account.trim()) issue("account", "Enter the account number.");
        else if (uk.errors.account) issue("account", uk.errors.account);
      } else if (!values.account.trim()) {
        issue("account", "Enter the account number.");
      }
    });
}

export type RecipientValues = z.input<ReturnType<typeof recipientSchema>>;

export const EMPTY_RECIPIENT: RecipientValues = {
  type: "UNIVERSITY",
  name: "",
  country: "GB",
  bic: "",
  ukMode: "iban",
  iban: "",
  account: "",
  routing: "",
};

/** What the form fills in for "Fill a synthetic example". */
export const EXAMPLE_RECIPIENT: RecipientValues = {
  ...EMPTY_RECIPIENT,
  name: EXAMPLE.name,
  bic: EXAMPLE.bic,
  iban: EXAMPLE.iban,
};

export function recipientBody(
  values: RecipientValues,
  corridor: Corridor | undefined,
): Record<string, string> {
  const body: Record<string, string> = {
    type: values.type,
    display_name: values.name.trim(),
    country: values.country,
    bic: values.bic.trim().toUpperCase(),
  };
  if (usesIban(corridor, values.ukMode)) body.iban = normalizeIban(values.iban);
  else {
    body.account_number = values.account.replace(/\s/g, "");
    const routing = values.routing.replace(/[\s-]/g, "");
    if (routing) body.routing_code = routing;
  }
  return body;
}
