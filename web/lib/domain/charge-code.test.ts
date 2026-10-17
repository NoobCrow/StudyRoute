import { describe, expect, it } from "vitest";

import { CHARGE_CODES, chargeCodeAdvice, chargeCodeLabel } from "@/lib/domain/charge-code";

describe("chargeCodeAdvice", () => {
  it("recommends OUR for tuition and says so", () => {
    const advice = chargeCodeAdvice("OUR", "TUITION");
    expect(advice.recommended).toBe(true);
    expect(advice.risk).toBe("low");
    expect(advice.badge).toBe("Recommended for tuition");
    expect(advice.explanation).toBe(
      "You pay every fee. The university should receive the full invoice amount. Best for tuition.",
    );
  });

  it("does not claim OUR is recommended for living costs, but keeps its low risk", () => {
    const advice = chargeCodeAdvice("OUR", "LIVING");
    expect(advice.recommended).toBe(false);
    expect(advice.risk).toBe("low");
    expect(advice.badge).toBe("Lowest short-payment risk");
  });

  it("warns that SHA may leave the university short, for any purpose", () => {
    for (const purpose of ["TUITION", "LIVING"] as const) {
      const advice = chargeCodeAdvice("SHA", purpose);
      expect(advice.recommended).toBe(false);
      expect(advice.risk).toBe("medium");
      expect(advice.badge).toBe("May arrive short");
      expect(advice.explanation).toContain("so the university may receive less");
    }
  });

  it("marks BEN as the highest short-payment risk", () => {
    const advice = chargeCodeAdvice("BEN", "TUITION");
    expect(advice.risk).toBe("high");
    expect(advice.badge).toBe("Highest short-payment risk");
    expect(advice.explanation).toBe(
      "The beneficiary pays everything. This has the highest risk of a short payment.",
    );
  });

  it("covers every code, once, in the order OUR, SHA, BEN", () => {
    expect(CHARGE_CODES).toEqual(["OUR", "SHA", "BEN"]);
    expect(CHARGE_CODES.map((code) => chargeCodeAdvice(code, "TUITION").code)).toEqual([
      "OUR",
      "SHA",
      "BEN",
    ]);
  });
});

describe("chargeCodeLabel", () => {
  it("names each code with who pays", () => {
    expect(chargeCodeLabel("OUR")).toBe("OUR (sender pays all)");
    expect(chargeCodeLabel("SHA")).toBe("SHA (shared)");
    expect(chargeCodeLabel("BEN")).toBe("BEN (beneficiary pays)");
  });
});
