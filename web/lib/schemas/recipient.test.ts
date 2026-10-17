import { describe, expect, it } from "vitest";

import { corridor } from "@/tests/fixtures";

import {
  EMPTY_RECIPIENT,
  EXAMPLE_RECIPIENT,
  recipientBody,
  recipientSchema,
  usesIban,
} from "./recipient";

const gb = corridor({ account_scheme: "IBAN" });
const ukDomestic = corridor({ country: "GB", account_scheme: "IBAN_OR_UK_DOMESTIC" });
const us = corridor({ country: "US", currency: "USD", account_scheme: "ABA_ACCOUNT" });
const filled = { ...EMPTY_RECIPIENT, name: "University of Example", bic: "exmpgb2l" };

function problems(
  values: Partial<typeof filled>,
  scheme = gb,
  mode: "iban" | "domestic" = "iban",
): Record<string, string> {
  const result = recipientSchema(scheme, mode).safeParse({ ...filled, ...values });
  if (result.success) return {};
  return Object.fromEntries(result.error.issues.map((i) => [i.path.join("."), i.message]));
}

describe("recipient schema follows the country's account scheme", () => {
  it("needs an IBAN where the scheme is IBAN, and checks its digits", () => {
    expect(problems({})).toEqual({ iban: "Enter the IBAN." });
    expect(problems({ iban: "GB08EXMP12345612344821" })).toEqual({});
    expect(problems({ iban: "GB09EXMP12345612344821" }).iban).toContain(
      "check digits do not match",
    );
    expect(problems({ iban: "gb08 exmp 1234 5612 3448 21" })).toEqual({});
  });

  it("needs a sort code and an 8-digit account for the UK domestic format", () => {
    expect(problems({}, ukDomestic, "domestic")).toEqual({
      routing: "Enter the sort code.",
      account: "Enter the account number.",
    });
    expect(problems({ routing: "12-34-5", account: "123" }, ukDomestic, "domestic")).toEqual({
      routing: "A sort code has 6 digits.",
      account: "A UK account number has 8 digits.",
    });
    expect(problems({ routing: "12-34-56", account: "12345678" }, ukDomestic, "domestic")).toEqual(
      {},
    );
    expect(usesIban(ukDomestic, "iban")).toBe(true);
    expect(usesIban(ukDomestic, "domestic")).toBe(false);
  });

  it("only asks for an account number where the scheme has no IBAN", () => {
    expect(problems({ country: "US", bic: "EXMPUS6C" }, us)).toEqual({
      account: "Enter the account number.",
    });
    expect(problems({ country: "US", bic: "EXMPUS6C", account: "000123456789" }, us)).toEqual({});
  });

  it("upper-cases the BIC and says what is wrong with it", () => {
    expect(
      recipientSchema(gb, "iban").parse({ ...filled, iban: "GB08EXMP12345612344821" }).bic,
    ).toBe("EXMPGB2L");
    expect(problems({ bic: "NOPE", iban: "GB08EXMP12345612344821" }).bic).toBe(
      "A BIC has 8 or 11 characters.",
    );
    expect(problems({ bic: "EXMPIE2L", iban: "GB08EXMP12345612344821" }).bic).toBe(
      "The country letters in the BIC must match the country.",
    );
  });

  it("wants a name of 1 to 140 characters, trimmed", () => {
    const iban = "GB08EXMP12345612344821";
    expect(problems({ name: "   ", iban }).name).toBe("Enter the recipient's name.");
    expect(problems({ name: "x".repeat(141), iban }).name).toContain("at most 140");
    expect(problems({ name: "x".repeat(140), iban })).toEqual({});
  });

  it("the synthetic example is valid as it is", () => {
    expect(recipientSchema(gb, "iban").safeParse(EXAMPLE_RECIPIENT).success).toBe(true);
    expect(EXAMPLE_RECIPIENT.iban).toBe("GB08EXMP12345612344821");
  });
});

describe("recipientBody", () => {
  it("sends only the fields the scheme uses, normalised", () => {
    expect(recipientBody({ ...filled, iban: " gb08 exmp " }, gb)).toEqual({
      type: "UNIVERSITY",
      display_name: "University of Example",
      country: "GB",
      bic: "EXMPGB2L",
      iban: "GB08EXMP",
    });
    expect(
      recipientBody(
        { ...filled, ukMode: "domestic", account: "1234 5678", routing: "12-34-56" },
        ukDomestic,
      ),
    ).toMatchObject({ account_number: "12345678", routing_code: "123456" });
  });
});
