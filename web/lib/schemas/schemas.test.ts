import { describe, expect, it } from "vitest";
import { z } from "zod";

import { signInSchema } from "./auth";
import { chargeCodes, moneyText, wholeMonths } from "./money";

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
