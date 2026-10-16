import { describe, expect, it } from "vitest";
import { z } from "zod";

import { corridor } from "@/tests/fixtures";

import { signInSchema } from "./auth";
import { chargeCodes, moneyText, wholeMonths } from "./money";
import { EMPTY_RECIPIENT, recipientBody, recipientSchema, usesIban } from "./recipient";

describe("sign-in schema", () => {
  it("asks for an email and a password", () => {
    const result = signInSchema.safeParse({ email: "", password: "" });
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.message)).toEqual([
      "Enter your email.",
      "Enter your password.",
    ]);
  });

  it("refuses something that is not an email and trims the one that is", () => {
    expect(signInSchema.safeParse({ email: "not-an-email", password: "x" }).success).toBe(false);
    expect(
      signInSchema.parse({ email: "  parent@demo.studyroute.test ", password: "x" }).email,
    ).toBe("parent@demo.studyroute.test");
  });
});

describe("money fields", () => {
  const field = z.object({ amount: moneyText("Amount", () => 2) });
  const zero = z.object({ amount: moneyText("Amount", () => 0) });

  it("accepts what a person types, with a comma", () => {
    expect(field.safeParse({ amount: "10,000.50" }).success).toBe(true);
  });

  it("says what is wrong, naming the field", () => {
    const result = field.safeParse({ amount: "ten" });
    expect(result.error?.issues[0]?.message).toMatch(/^Amount: Use digits only/);
  });

  it("rejects too many decimals and zero", () => {
    expect(field.safeParse({ amount: "1.234" }).success).toBe(false);
    expect(field.safeParse({ amount: "0" }).success).toBe(false);
  });

  it("uses the currency's own decimals (JPY has none)", () => {
    expect(zero.safeParse({ amount: "1000" }).success).toBe(true);
    expect(zero.safeParse({ amount: "1000.5" }).success).toBe(false);
  });

  it("limits months to a whole number from 1 to 60", () => {
    expect(wholeMonths.safeParse("12").success).toBe(true);
    for (const bad of ["0", "61", "1.5", "x", ""])
      expect(wholeMonths.safeParse(bad).success).toBe(false);
  });

  it("knows the three charge codes", () => {
    expect(chargeCodes).toEqual(["OUR", "SHA", "BEN"]);
  });
});

describe("recipient schema follows the country's account scheme", () => {
  const gb = corridor({ account_scheme: "IBAN" });
  const ukDomestic = corridor({ country: "GB", account_scheme: "IBAN_OR_UK_DOMESTIC" });
  const filled = { ...EMPTY_RECIPIENT, name: "University of Example", bic: "exmpgb2l" };

  it("needs an IBAN where the scheme is IBAN", () => {
    const result = recipientSchema(gb, "iban").safeParse(filled);
    expect(result.error?.issues.map((i) => i.path.join("."))).toEqual(["iban"]);
    expect(
      recipientSchema(gb, "iban").safeParse({ ...filled, iban: "GB08EXMP12345612344821" }).success,
    ).toBe(true);
  });

  it("needs an account number for the UK domestic format", () => {
    expect(
      recipientSchema(ukDomestic, "domestic").safeParse(filled).error?.issues[0]?.path,
    ).toEqual(["account"]);
    expect(usesIban(ukDomestic, "iban")).toBe(true);
    expect(usesIban(ukDomestic, "domestic")).toBe(false);
  });

  it("upper-cases and checks the BIC", () => {
    expect(recipientSchema(gb, "iban").parse({ ...filled, iban: "x" }).bic).toBe("EXMPGB2L");
    expect(
      recipientSchema(gb, "iban").safeParse({ ...filled, bic: "NOPE", iban: "x" }).success,
    ).toBe(false);
  });

  it("sends only the fields the scheme uses", () => {
    expect(recipientBody({ ...filled, iban: " GB08 " }, gb)).toEqual({
      type: "UNIVERSITY",
      display_name: "University of Example",
      country: "GB",
      bic: "EXMPGB2L",
      iban: "GB08",
    });
    expect(
      recipientBody(
        { ...filled, ukMode: "domestic", account: "12345678", routing: "123456" },
        ukDomestic,
      ),
    ).toMatchObject({
      account_number: "12345678",
      routing_code: "123456",
    });
  });
});
