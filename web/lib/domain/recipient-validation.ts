// Checks a person can see while they type. The server checks the same things again and is the authority:
// nothing here approves anything, it only spares a round trip and says what is wrong in words.

export type Check<T = string> = { ok: true; value: T } | { ok: false; message: string };

export const BIC_HELP = "8 or 11 characters. The country letters must match.";
export const IBAN_VALID = "The check digits are verified (ISO 13616, mod 97).";

const BIC_SHAPE = /^[A-Z0-9]{8}([A-Z0-9]{3})?$/;

/** Uppercase, 8 or 11 letters and digits, and characters 5 and 6 must be the destination's country code. */
export function validateBic(bic: string, countryCode: string): Check {
  const value = bic.trim().toUpperCase();
  if (!BIC_SHAPE.test(value)) return { ok: false, message: "A BIC has 8 or 11 characters." };
  if (value.slice(4, 6) !== countryCode.toUpperCase()) {
    return { ok: false, message: "The country letters in the BIC must match the country." };
  }
  return { ok: true, value };
}

/** An IBAN without spaces, in capitals. */
export function normalizeIban(iban: string): string {
  return iban.replace(/\s+/g, "").toUpperCase();
}

/**
 * ISO 13616: move the first four characters to the end, turn letters into numbers (A=10 ... Z=35) and
 * the remainder after dividing by 97 must be 1. The remainder is carried digit by digit, so no number
 * ever gets big enough to lose precision.
 */
export function ibanCheckDigitsHold(iban: string): boolean {
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  let remainder = 0;
  for (const char of rearranged) {
    const digits = /[A-Z]/.test(char) ? String(char.charCodeAt(0) - 55) : char;
    for (const digit of digits) remainder = (remainder * 10 + Number(digit)) % 97;
  }
  return remainder === 1;
}

export function validateIban(iban: string, countryCode: string): Check {
  const value = normalizeIban(iban);
  if (!/^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/.test(value)) {
    return {
      ok: false,
      message: "An IBAN starts with two letters and two digits, then up to 30 letters and digits.",
    };
  }
  if (value.slice(0, 2) !== countryCode.toUpperCase()) {
    return {
      ok: false,
      message: `The IBAN must start with the country letters ${countryCode.toUpperCase()}.`,
    };
  }
  if (!ibanCheckDigitsHold(value)) {
    return {
      ok: false,
      message: "The check digits do not match. Check the IBAN and try again.",
    };
  }
  return { ok: true, value };
}

export interface UkAccountResult {
  ok: boolean;
  sortCode: string;
  account: string;
  errors: { sortCode?: string; account?: string; country?: string };
}

/** A UK sort code (6 digits, dashes allowed) and account number (8 digits). Only for the United Kingdom. */
export function validateUkAccount(
  sortCode: string,
  accountNumber: string,
  countryCode: string,
): UkAccountResult {
  const code = sortCode.replace(/[\s-]/g, "");
  const account = accountNumber.replace(/\s/g, "");
  const errors: UkAccountResult["errors"] = {};
  if (countryCode.toUpperCase() !== "GB") {
    errors.country = "A sort code and account number are only used in the United Kingdom.";
  }
  if (!/^[0-9]{6}$/.test(code)) errors.sortCode = "A sort code has 6 digits.";
  if (!/^[0-9]{8}$/.test(account)) errors.account = "A UK account number has 8 digits.";
  return { ok: Object.keys(errors).length === 0, sortCode: code, account, errors };
}
