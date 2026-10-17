// Turns what a person types ("10,000.50") into integer minor units WITHOUT floating point.
// This is input parsing, not calculation: every amount shown on screen comes from the backend.

export type ParsedMoney = { ok: true; minor: number } | { ok: false; error: string };

const MAX_MINOR = 10 ** 12;

export function parseMajorToMinor(input: string, exponent = 2): ParsedMoney {
  const cleaned = input.trim().replace(/[\s,]/g, "");
  if (cleaned === "") return { ok: false, error: "Enter an amount." };
  const decimals = exponent > 0 ? `(?:[.]([0-9]{1,${exponent}}))?` : "()";
  const match = new RegExp(`^([0-9]{1,12})${decimals}$`).exec(cleaned);
  if (!match) {
    return {
      ok: false,
      error:
        exponent > 0
          ? `Use digits only, with at most ${exponent} decimal places.`
          : "Use whole numbers only: this currency has no decimals.",
    };
  }
  const whole = match[1] ?? "0";
  const fraction = (match[2] ?? "").padEnd(exponent, "0");
  const minor = Number(whole + fraction);
  if (minor <= 0) return { ok: false, error: "The amount must be greater than zero." };
  if (minor > MAX_MINOR) return { ok: false, error: "That amount is too large for the sandbox." };
  return { ok: true, minor };
}

/**
 * Echoes an amount the person typed, with thousands separators ("10,000", "10,000.50"). It only lays
 * out digits that were already there; the whole part and the decimals are cut from the integer text.
 */
export function formatMinorCompact(minor: number, exponent = 2): string {
  const digits = String(Math.max(0, Math.trunc(minor))).padStart(exponent + 1, "0");
  const whole = digits.slice(0, digits.length - exponent);
  const fraction = exponent > 0 ? digits.slice(-exponent) : "";
  const grouped = whole.replace(/\B(?=([0-9]{3})+(?![0-9]))/g, ",");
  return /^0*$/.test(fraction) ? grouped : `${grouped}.${fraction}`;
}
