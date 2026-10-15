import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { DeadlineFit, Quote } from "../api/types";
import { PLAN_CARD, QUOTE, result } from "../test/fixtures";
import { PlanCard } from "./PlanCard";
import { QuoteTable } from "./QuoteTable";

const NOTE = "Indicative. Confirm with your AD bank.";

function fit(overrides: Partial<DeadlineFit>): DeadlineFit {
  return {
    due_date: "2026-10-15", send_date: "2026-10-14",
    best_in_time: "prov_a", cheapest_overall: "prov_b", cheapest_misses_deadline: true, fastest: "prov_a",
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
    results: [result(1, "prov_b", "Provider B (synthetic)"), result(2, "prov_a", "Provider A (synthetic)")],
    deadline_fit: deadline,
  };
}

describe("QuoteTable with a deadline", () => {
  it("passes over the cheapest provider when it would arrive late and says which one is in time", () => {
    render(<QuoteTable quote={quoteWith(fit({}))} selected="prov_a" />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Provider B (synthetic) has the lowest cost but would arrive after",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("The cheapest provider that arrives in time is Provider A (synthetic)");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Too late");
    expect(rows[1]).toHaveTextContent("In time");
    expect(rows[1]).toHaveTextContent("Best in time");
    expect(rows[1]).toHaveClass("best");
    expect(rows[0]).not.toHaveClass("best");
  });

  it("says so when nobody can arrive by the due date", () => {
    const none = fit({ best_in_time: null, fastest: "prov_a" });
    render(<QuoteTable quote={quoteWith(none)} selected={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("No provider can arrive by");
    expect(screen.getByRole("alert")).toHaveTextContent("The fastest is Provider A (synthetic)");
  });

  it("stays quiet about a comfortable deadline and keeps the lowest cost on top", () => {
    const calm = fit({
      best_in_time: "prov_b", cheapest_misses_deadline: false,
      providers: [
        { provider_id: "prov_b", arrives_on: "2026-10-19", meets_deadline: true, days_to_spare: 9 },
        { provider_id: "prov_a", arrives_on: "2026-10-15", meets_deadline: true, days_to_spare: 13 },
      ],
    });
    render(<QuoteTable quote={quoteWith(calm)} selected="prov_b" />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(NOTE);
    expect(screen.getAllByRole("row")[1]).toHaveClass("best");
  });

  it("shows no arrival dates when the quote has no due date", () => {
    render(<QuoteTable quote={quoteWith(null)} selected={null} />);
    expect(screen.queryByText(/arrives/i)).toBeNull();
    expect(screen.getByText("Days")).toBeInTheDocument();
  });

  it("puts the arrival date under the provider name instead of widening the table", () => {
    render(<QuoteTable quote={quoteWith(fit({}))} selected="prov_a" />);
    expect(screen.queryByText("Arrives")).toBeNull();
    expect(screen.getAllByRole("row")[2]).toHaveTextContent(/Arrives .*15/);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toContain("Days");
  });
});

describe("PlanCard with a deadline", () => {
  it("shows when the proposed provider arrives and which one was passed over", () => {
    const card = {
      ...PLAN_CARD,
      cheapest_misses_deadline: true,
      deadline_fit: fit({}),
      best: { ...PLAN_CARD.best, provider_name: "Provider A (synthetic)", arrives_on: "2026-10-15", meets_deadline: true },
      alternatives: [
        { ...PLAN_CARD.best, provider_id: "prov_b", provider_name: "Provider B (synthetic)", meets_deadline: false },
      ],
    };
    render(<MemoryRouter><PlanCard card={card} /></MemoryRouter>);
    expect(screen.getByText("Lowest cost that arrives in time")).toBeInTheDocument();
    expect(screen.getByText("in time")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Provider B (synthetic) would arrive after the due date.");
  });
});
