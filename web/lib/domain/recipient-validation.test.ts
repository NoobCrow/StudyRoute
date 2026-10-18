import { describe, expect, it } from "vitest";

import {
  BIC_HELP,
  IBAN_VALID,
  ibanCheckDigitsHold,
  normalizeIban,
  validateBic,
  validateIban,
  validateUkAccount,
} from "@/lib/domain/recipient-validation";

describe("validateBic", () => {
  it("accepts 8 and 11 characters whose letters 5 and 6 are the country, and uppercases them", () => {
    expect(validateBic("EXMPGB2L", "GB")).toEqual({ ok: true, value: "EXMPGB2L" });
    expect(validateBic("exmpgb2lxxx", "GB")).toEqual({ ok: true, value: "EXMPGB2LXXX" });
    expect(validateBic("  EXMPGB2L ", "gb")).toEqual({ ok: true, value: "EXMPGB2L" });
  });

  it("says a BIC has 8 or 11 characters when the length or the characters are wrong", () => {
    const message = "A BIC has 8 or 11 characters.";
    expect(validateBic("EXMPGB2", "GB")).toEqual({ ok: false, message });
    expect(validateBic("EXMPGB2LX", "GB")).toEqual({ ok: false, message });
    expect(validateBic("EXMP-B2L", "GB")).toEqual({ ok: false, message });
    expect(validateBic("", "GB")).toEqual({ ok: false, message });
  });

  it("says the country letters must match", () => {
    expect(validateBic("EXMPIE2L", "GB")).toEqual({
      ok: false,
      message: "The country letters in the BIC must match the country.",
    });
  });

  it("has the design's neutral help text", () => {
    expect(BIC_HELP).toBe("8 or 11 characters. The country letters must match.");
  });
});

describe("validateIban", () => {
  it("accepts the sandbox example, with spaces and in lower case", () => {
    expect(validateIban("GB08EXMP12345612344821", "GB")).toEqual({
      ok: true,
      value: "GB08EXMP12345612344821",
    });
    expect(validateIban("gb08 exmp 1234 5612 3448 21", "GB")).toEqual({
      ok: true,
      value: "GB08EXMP12345612344821",
    });
    expect(IBAN_VALID).toBe("The check digits are verified (ISO 13616, mod 97).");
  });

  it("rejects wrong check digits with the design's words", () => {
    expect(validateIban("GB09EXMP12345612344821", "GB")).toEqual({
      ok: false,
      message: "The check digits do not match. Check the IBAN and try again.",
    });
  });

  it("rejects an IBAN of another country", () => {
    const result = validateIban("DE89370400440532013000", "GB");
    expect(result.ok).toBe(false);
    expect(!result.ok && result.message).toContain("must start with the country letters GB");
  });

  it("rejects the wrong shape before looking at digits", () => {
    for (const bad of [
      "",
      "GB08",
      "1234567890123456",
      "GB08EXMP1234!6123448",
      "GB0AEXMP12345612344821",
    ]) {
      expect(validateIban(bad, "GB").ok).toBe(false);
    }
  });

  it("checks known real-format examples without big integers", () => {
    expect(ibanCheckDigitsHold("DE89370400440532013000")).toBe(true);
    expect(ibanCheckDigitsHold("FR1420041010050500013M02606")).toBe(true);
    expect(ibanCheckDigitsHold("DE89370400440532013001")).toBe(false);
  });

  it("strips spaces and capitals the same way everywhere", () => {
    expect(normalizeIban(" gb08 exmp\t1234 ")).toBe("GB08EXMP1234");
  });
});

describe("validateUkAccount", () => {
  it("accepts a 6-digit sort code (dashes allowed) and an 8-digit account in the United Kingdom", () => {
    expect(validateUkAccount("12-34-56", "12345678", "GB")).toEqual({
      ok: true,
      sortCode: "123456",
      account: "12345678",
      errors: {},
    });
    expect(validateUkAccount("123456", "12345678", "gb").ok).toBe(true);
  });

  it("says what is wrong with each field", () => {
    const result = validateUkAccount("12345", "1234567", "GB");
    expect(result.ok).toBe(false);
    expect(result.errors.sortCode).toBe("A sort code has 6 digits.");
    expect(result.errors.account).toBe("A UK account number has 8 digits.");
    expect(validateUkAccount("12345a", "12345678", "GB").errors.sortCode).toBeDefined();
  });

  it("is only valid when the country is the United Kingdom", () => {
    const result = validateUkAccount("123456", "12345678", "IE");
    expect(result.ok).toBe(false);
    expect(result.errors.country).toContain("only used in the United Kingdom");
  });
});
