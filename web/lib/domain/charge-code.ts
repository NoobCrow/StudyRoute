import type { ChargeCode } from "@/lib/api/types";

// Words only: which charge code carries which risk. No amount is worked out here. The fees themselves
// and any shortfall come from the engine; this explains who pays them.

export type Purpose = "TUITION" | "LIVING";
export type RiskLevel = "low" | "medium" | "high";

export interface ChargeCodeAdvice {
  code: ChargeCode;
  /** Who pays the fees on the way, in words. */
  who: string;
  risk: RiskLevel;
  /** The text of the badge on the card. */
  badge: string;
  /** True for the code the app suggests for this purpose (OUR for tuition). */
  recommended: boolean;
  explanation: string;
}

export const CHARGE_CODES: readonly ChargeCode[] = ["OUR", "SHA", "BEN"];

const WHO: Record<ChargeCode, string> = {
  OUR: "sender pays all",
  SHA: "shared",
  BEN: "beneficiary pays",
};

const EXPLANATION: Record<ChargeCode, string> = {
  OUR: "Sender pays the modelled fees. Full arrival is not guaranteed: confirm the accepted payment route and charges.",
  SHA: "You pay your bank. Correspondent and receiving fees are taken from the amount, so the university may receive less.",
  BEN: "The beneficiary pays everything. This has the highest risk of a short payment.",
};

export function chargeCodeAdvice(code: ChargeCode, purpose: Purpose): ChargeCodeAdvice {
  const recommended = code === "OUR" && purpose === "TUITION";
  const advice = { code, who: WHO[code], explanation: EXPLANATION[code], recommended };
  if (code === "OUR") {
    return {
      ...advice,
      risk: "low",
      badge: recommended ? "Recommended for tuition" : "Lowest short-payment risk",
    };
  }
  if (code === "SHA") return { ...advice, risk: "medium", badge: "May arrive short" };
  return { ...advice, risk: "high", badge: "Highest short-payment risk" };
}

/** "OUR (sender pays all)": how a code is named in summaries. */
export function chargeCodeLabel(code: ChargeCode): string {
  return `${code} (${WHO[code]})`;
}
