// Turns what a person types ("10,000.50") into integer minor units WITHOUT floating point.
// This is input parsing, not calculation: every amount shown on screen comes from the backend.

export type ParsedMoney = { ok: true; minor: number } | { ok: false; error: string };

const MAX_MINOR = 10 ** 12;

export function parseMajorToMinor(input: string, exponent = 2): ParsedMoney {
  const cleaned = input.trim().replace(/[\s,]/g, "");
  if (cleaned === "") return { ok: false, error: "Enter an amount." };
  const pattern = new RegExp(`^([0-9]{1,12})(?:[.]([0-9]{1,${exponent}}))?$`);
  const match = pattern.exec(cleaned);
  if (!match) {
    return { ok: false, error: `Use digits only, with at most ${exponent} decimal places.` };
  }
  const whole = match[1] ?? "0";
  const fraction = (match[2] ?? "").padEnd(exponent, "0");
  const minor = Number(whole + fraction);
  if (minor <= 0) return { ok: false, error: "The amount must be greater than zero." };
  if (minor > MAX_MINOR) return { ok: false, error: "That amount is too large for the sandbox." };
  return { ok: true, minor };
}
