import { afterEach, describe, expect, it, vi } from "vitest";

import { QuoteTable } from "@/components/compare/quote-table";
import type { Quote } from "@/lib/api/types";
import { QUOTE, result } from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

afterEach(() => vi.unstubAllGlobals());

/** Three providers with different true total costs: B best, C cheap but short, A dearest. */
function quote(): Quote {
  return {
    ...QUOTE,
    deadline_fit: null,
    results: [
      { ...result(1, "prov_b", "Provider B (synthetic)"), total_cost_bdt_minor: 2_530_000 },
      { ...result(2, "prov_c", "Provider C (synthetic)", 3_500), total_cost_bdt_minor: 2_610_000 },
      { ...result(3, "prov_a", "Provider A (synthetic)"), total_cost_bdt_minor: 3_450_000 },
    ],
  };
}

function bars(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(".animate-grow-x")];
}

describe("QuoteTable cost bars", () => {
  it("draws one bar per provider, the dearest at full length and the others in proportion", () => {
    const { container } = renderWithProviders(<QuoteTable quote={quote()} selected={null} />);
    expect(bars(container).map((bar) => bar.style.width)).toEqual(["73%", "76%", "100%"]);
  });

  it("colours the best provider green, a short payment red and the rest quietly", () => {
    const { container } = renderWithProviders(<QuoteTable quote={quote()} selected={null} />);
    const [best, short, other] = bars(container);
    expect(best).toHaveClass("bg-primary");
    expect(short).toHaveClass("bg-destructive");
    expect(other).toHaveClass("bg-primary/45");
  });

  it("is only decoration: hidden from screen readers, with every amount in the text", () => {
    const { container } = renderWithProviders(<QuoteTable quote={quote()} selected={null} />);
    for (const bar of bars(container)) {
      expect(bar.parentElement).toHaveAttribute("aria-hidden", "true");
    }
    expect(container.textContent).toContain("Short by GBP 35.00");
  });

  it("never draws a bar too short to see", () => {
    const tiny: Quote = {
      ...quote(),
      results: [
        { ...result(1, "prov_b", "Provider B (synthetic)"), total_cost_bdt_minor: 1 },
        { ...result(2, "prov_a", "Provider A (synthetic)"), total_cost_bdt_minor: 9_000_000 },
      ],
    };
    const { container } = renderWithProviders(<QuoteTable quote={tiny} selected={null} />);
    expect(bars(container)[0]?.style.width).toBe("6%");
  });
});
