import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StressCard } from "@/components/compare/stress-card";
import { Countdown } from "@/components/compare/countdown";
import { QuoteTable } from "@/components/compare/quote-table";
import type { DeadlineFit, Quote } from "@/lib/api/types";
import { QUOTE, STRESS, mockApi, problem, result } from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

afterEach(() => vi.unstubAllGlobals());

const NOTE = "Indicative. Confirm with your AD bank.";

function fit(overrides: Partial<DeadlineFit>): DeadlineFit {
  return {
    due_date: "2026-10-15",
    send_date: "2026-10-14",
    best_in_time: "prov_a",
    cheapest_overall: "prov_b",
    cheapest_misses_deadline: true,
    fastest: "prov_a",
    providers: [
      { provider_id: "prov_b", arrives_on: "2026-10-19", meets_deadline: false, days_to_spare: -4 },
      { provider_id: "prov_a", arrives_on: "2026-10-15", meets_deadline: true, days_to_spare: 0 },
    ],
    indicative: NOTE,
    ...overrides,
  };
}

function quoteWith(deadline: DeadlineFit | null): Quote {
  return {
    ...QUOTE,
    results: [
      result(1, "prov_b", "Provider B (synthetic)"),
      result(2, "prov_a", "Provider A (synthetic)"),
    ],
    deadline_fit: deadline,
  };
}

describe("QuoteTable", () => {
  it("ranks providers and shows the shortfall as a red warning", () => {
    render(<QuoteTable quote={QUOTE} selected="prov_b" />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Provider B");
    expect(rows[0]).toHaveTextContent("Lowest cost");
    expect(rows[1]).toHaveTextContent("Provider C");
    expect(screen.getByRole("alert")).toHaveTextContent("Short by GBP 35.00");
  });

  it("shows only values formatted by the server (no client-side money maths)", () => {
    render(<QuoteTable quote={QUOTE} selected={null} />);
    expect(screen.getAllByText("BDT 1,625,300.00").length).toBeGreaterThan(0);
  });

  it("offers one radio per provider when the person can choose", () => {
    render(<QuoteTable quote={QUOTE} selected="prov_b" onSelect={vi.fn()} />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(screen.getByRole("radio", { name: "Choose Provider B (synthetic)" })).toBeChecked();
  });

  it("tells the parent who to choose when the cheapest would arrive late", () => {
    render(<QuoteTable quote={quoteWith(fit({}))} selected="prov_a" onSelect={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Provider B (synthetic) has the lowest cost but would arrive after",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The cheapest provider that arrives in time is Provider A (synthetic)",
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Too late");
    expect(rows[1]).toHaveTextContent("In time");
    expect(rows[1]).toHaveTextContent("Best in time");
    expect(rows[1]).toHaveAttribute("data-best", "true");
    expect(rows[0]).not.toHaveAttribute("data-best");
  });

  it("says so when nobody can arrive by the due date", () => {
    render(
      <QuoteTable
        quote={quoteWith(fit({ best_in_time: null, fastest: "prov_a" }))}
        selected={null}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("No provider can arrive by");
    expect(screen.getByRole("alert")).toHaveTextContent("The fastest is Provider A (synthetic)");
  });

  it("stays quiet about a comfortable deadline and keeps the lowest cost on top", () => {
    const calm = fit({
      best_in_time: "prov_b",
      cheapest_misses_deadline: false,
      providers: [
        { provider_id: "prov_b", arrives_on: "2026-10-19", meets_deadline: true, days_to_spare: 9 },
        {
          provider_id: "prov_a",
          arrives_on: "2026-10-15",
          meets_deadline: true,
          days_to_spare: 13,
        },
      ],
    });
    render(<QuoteTable quote={quoteWith(calm)} selected="prov_b" />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(NOTE);
    expect(screen.getAllByRole("row")[1]).toHaveAttribute("data-best", "true");
  });

  it("shows no arrival dates when the quote has no due date", () => {
    render(<QuoteTable quote={quoteWith(null)} selected={null} />);
    expect(screen.queryByText(/arrives/i)).toBeNull();
  });

  it("puts the arrival date under the provider name instead of widening the table", () => {
    render(<QuoteTable quote={quoteWith(fit({}))} selected="prov_a" />);
    expect(screen.getAllByRole("row")[2]).toHaveTextContent(/Arrives .*15/);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toContain("Days");
  });
});

describe("Countdown", () => {
  it("says the quote expired once the time has passed", () => {
    render(<Countdown expiresAt="2000-01-01T00:00:00Z" />);
    expect(screen.getByText("Quote expired")).toBeInTheDocument();
  });

  it("shows the time left while the quote is valid", () => {
    render(<Countdown expiresAt="2099-01-01T00:00:00Z" />);
    expect(screen.getByText(/^Valid for/)).toBeInTheDocument();
  });
});

describe("StressCard", () => {
  it("shows today and each what-if with the extra taka, all formatted by the server", async () => {
    const fetcher = mockApi({ "/quotes/qte_1/stress": STRESS });
    renderWithProviders(<StressCard quoteId="qte_1" providerId="prov_b" />);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Today");
    expect(rows[0]).toHaveTextContent("BDT 1,625,300.00");
    expect(rows[1]).toHaveTextContent("5% more taka");
    expect(rows[1]).toHaveTextContent("BDT 84,000.00 (5.17%)");
    expect(rows[2]).toHaveTextContent("BDT 1,793,300.00");
    expect(String(fetcher.mock.calls[0]?.[0])).toContain("/quotes/qte_1/stress?provider_id=prov_b");
  });

  it("says it is a what-if on synthetic rates and not a forecast", async () => {
    mockApi({ "/quotes/qte_1/stress": STRESS });
    renderWithProviders(<StressCard quoteId="qte_1" providerId="prov_b" />);
    expect(await screen.findByText(/not a forecast/)).toBeInTheDocument();
    expect(screen.getByText(/Indicative\. Confirm with your AD bank\./)).toBeInTheDocument();
  });

  it("shows the problem instead of guessing when the server refuses", async () => {
    mockApi({ "/quotes/qte_1/stress": problem(404, "NOT_FOUND", "Quote not found.") });
    renderWithProviders(<StressCard quoteId="qte_1" providerId="prov_b" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Quote not found.");
  });
});
