import { z } from "zod";

import type { Corridor } from "@/lib/api/types";

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

/** The recipient form. Which account fields are required depends on the country's account scheme. */
export function recipientSchema(corridor: Corridor | undefined, ukMode: UkMode) {
  const iban = usesIban(corridor, ukMode);
  return z
    .object({
      type: z.enum(["UNIVERSITY", "STUDENT"]),
      name: z.string().trim().min(2, "Enter the recipient's name.").max(120),
      country: z.string().min(1),
      bic: z
        .string()
        .trim()
        .transform((value) => value.toUpperCase())
        .refine(
          (value) => BIC_PATTERN.test(value),
          "A BIC has 8 or 11 letters and digits, for example EXMPGB2L.",
        ),
      ukMode: z.enum(["iban", "domestic"]),
      iban: z.string(),
      account: z.string(),
      routing: z.string(),
    })
    .superRefine((values, ctx) => {
      if (iban && !values.iban.trim())
        ctx.addIssue({ code: "custom", path: ["iban"], message: "Enter the IBAN." });
      if (!iban && !values.account.trim()) {
        ctx.addIssue({ code: "custom", path: ["account"], message: "Enter the account number." });
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
  if (usesIban(corridor, values.ukMode)) body.iban = values.iban.trim();
  else {
    body.account_number = values.account.trim();
    if (values.routing.trim()) body.routing_code = values.routing.trim();
  }
  return body;
}
