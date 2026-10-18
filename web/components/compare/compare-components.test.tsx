import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StressCard } from "@/components/compare/stress-card";
import { Countdown } from "@/components/compare/countdown";
import { ChargeCodeCards } from "@/components/compare/charge-code-cards";
import { QuoteTable } from "@/components/compare/quote-table";
import { QuotesCard } from "@/components/compare/quotes-card";
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
  it("ranks providers, marks the best one and shows the shortfall as a red warning", () => {
    renderWithProviders(<QuoteTable quote={QUOTE} selected="prov_b" />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Provider B");
    expect(rows[0]).toHaveTextContent("Best");
    expect(rows[1]).toHaveTextContent("Provider C");
    expect(rows[1]).not.toHaveTextContent("Best");
    expect(screen.getByRole("alert")).toHaveTextContent("Short by GBP 35.00");
  });

  it("has the five columns of the design and an actions column", () => {
    renderWithProviders(<QuoteTable quote={QUOTE} selected={null} />);
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent?.trim());
    expect(heads.slice(0, 5)).toEqual([
      "Provider",
      "Exchange rate",
      "Fees",
      "Rate margin",
      "True total cost",
    ]);
  });

  it("shows only values formatted by the server (no client-side money maths)", () => {
    renderWithProviders(<QuoteTable quote={QUOTE} selected={null} />);
    const row = screen.getAllByRole("row")[1] as HTMLElement;
    expect(within(row).getByText("161.600000")).toBeInTheDocument();
    expect(within(row).getByText("BDT 3,000.00")).toBeInTheDocument();
    expect(within(row).getByText("BDT 1,500.00 SWIFT")).toBeInTheDocument();
    expect(within(row).getByText("1.00%")).toBeInTheDocument();
    expect(within(row).getByText("BDT 16,000.00")).toBeInTheDocument();
    expect(within(row).getByText("BDT 25,300.00")).toBeInTheDocument();
    expect(within(row).getByText(/you pay BDT 1,625,300.00/)).toBeInTheDocument();
  });

  it("explains the hidden margin in a tooltip on the column", async () => {
    renderWithProviders(<QuoteTable quote={QUOTE} selected={null} />);
    await userEvent.hover(screen.getByText("Rate margin"));
    expect((await screen.findAllByText(/The hidden margin/))[0]).toBeInTheDocument();
  });

  it("opens a breakdown from the row menu with every line the engine sent", async () => {
    renderWithProviders(<QuoteTable quote={QUOTE} selected={null} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Actions for Provider B (synthetic)" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "View breakdown" }));
    const sheet = await screen.findByRole("dialog", { name: "Provider B (synthetic)" });
    expect(within(sheet).getByText("Rate margin")).toBeInTheDocument();
    expect(within(sheet).getByText("Fixed fee")).toBeInTheDocument();
    expect(within(sheet).getByText("SWIFT fee")).toBeInTheDocument();
    expect(within(sheet).getByText("Correspondent fee")).toBeInTheDocument();
    expect(within(sheet).getByText("True total cost")).toBeInTheDocument();
    expect(within(sheet).getByText("BDT 1,625,300.00")).toBeInTheDocument();
    expect(within(sheet).getByText(/Indicative\. Confirm with your AD bank\./)).toBeInTheDocument();
  });

  it("offers Start payment only to someone who can draft, and says which provider", async () => {
    const onStart = vi.fn();
    const { unmount } = renderWithProviders(<QuoteTable quote={QUOTE} selected="prov_b" />);
    await userEvent.click(
      screen.getByRole("button", { name: "Actions for Provider C (synthetic)" }),
    );
    expect(await screen.findByRole("menuitem", { name: "View breakdown" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Start payment" })).toBeNull();
    unmount();

    renderWithProviders(<QuoteTable quote={QUOTE} selected="prov_b" onStart={onStart} />);
    expect(screen.getByText("Selected")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Actions for Provider C (synthetic)" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Start payment" }));
    expect(onStart).toHaveBeenCalledWith("prov_c");
  });

  it("tells the parent who to choose when the cheapest would arrive late", () => {
    renderWithProviders(
      <QuoteTable quote={quoteWith(fit({}))} selected="prov_a" onStart={vi.fn()} />,
    );
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
      "Provider B (synthetic) has the lowest cost but would arrive after",
    );
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
      "The cheapest provider that arrives in time is Provider A (synthetic)",
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Too late");
    expect(rows[0]).toHaveTextContent("Lowest cost");
    expect(rows[0]).not.toHaveTextContent("Best");
    expect(rows[1]).toHaveTextContent("In time");
    expect(rows[1]).toHaveTextContent("Best in time");
    expect(rows[1]).toHaveAttribute("data-best", "true");
    expect(rows[0]).not.toHaveAttribute("data-best");
  });

  it("says so when nobody can arrive by the due date", () => {
    renderWithProviders(
      <QuoteTable
        quote={quoteWith(fit({ best_in_time: null, fastest: "prov_a" }))}
        selected={null}
      />,
    );
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("No provider can arrive by");
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
      "The fastest is Provider A (synthetic)",
    );
  });

  it("stays quiet about a comfortable deadline and keeps the best one on top", () => {
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
    renderWithProviders(<QuoteTable quote={quoteWith(calm)} selected="prov_b" />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(NOTE);
    expect(screen.getAllByRole("row")[1]).toHaveAttribute("data-best", "true");
    expect(screen.getAllByRole("row")[1]).toHaveTextContent("Best");
  });

  it("shows no arrival dates when the quote has no due date", () => {
    renderWithProviders(<QuoteTable quote={quoteWith(null)} selected={null} />);
    expect(screen.queryByText(/arrives/i)).toBeNull();
  });

  it("puts the arrival date under the provider name instead of widening the table", () => {
    renderWithProviders(<QuoteTable quote={quoteWith(fit({}))} selected="prov_a" />);
    expect(screen.getAllByRole("row")[2]).toHaveTextContent(/Arrives .*15/);
  });
});

describe("QuotesCard", () => {
  const base = {
    busy: false,
    error: null,
    currency: "GBP",
    selected: null,
    onRetry: vi.fn(),
    headingRef: { current: null },
  };

  it("shows the empty state with the design's words and the same five columns", () => {
    renderWithProviders(<QuotesCard {...base} quote={null} />);
    expect(screen.getByText("Quotes")).toBeInTheDocument();
    expect(screen.getByText("Ranked by true total cost")).toBeInTheDocument();
    expect(screen.getByText("Synthetic data")).toBeInTheDocument();
    expect(
      screen.getByText("No quotes yet. Press Get quotes to rank providers by the true total cost."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").length).toBeGreaterThanOrEqual(5);
  });

  it("shows a busy status instead of the empty text while the providers are asked", () => {
    renderWithProviders(<QuotesCard {...base} quote={null} busy />);
    expect(screen.getByRole("status")).toHaveTextContent("Asking the synthetic providers");
    expect(screen.queryByText(/No quotes yet/)).toBeNull();
  });

  it("shows the problem with a Retry button when the quotes could not be fetched", async () => {
    const onRetry = vi.fn();
    renderWithProviders(
      <QuotesCard {...base} quote={null} error={new Error("Network down")} onRetry={onRetry} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Network down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the ranked table and the quote's own words once there is a quote", () => {
    renderWithProviders(<QuotesCard {...base} quote={QUOTE} selected="prov_b" />);
    expect(screen.getByRole("region", { name: "Provider comparison table" })).toBeInTheDocument();
    expect(screen.getByText(/Mid-market rate BDT 160.000000 per 1 GBP/)).toBeInTheDocument();
    expect(screen.queryByText(/No quotes yet/)).toBeNull();
  });
});

describe("ChargeCodeCards", () => {
  function setup(purpose: "TUITION" | "LIVING" = "TUITION", value: "OUR" | "SHA" | "BEN" = "OUR") {
    const onChange = vi.fn();
    renderWithProviders(<ChargeCodeCards value={value} onChange={onChange} purpose={purpose} />);
    return onChange;
  }

  it("is a fieldset with a legend and three radio cards, OUR first and chosen", () => {
    setup();
    expect(screen.getByRole("group", { name: "Charge code" })).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("value"))).toEqual(["OUR", "SHA", "BEN"]);
    expect(radios[0]).toBeChecked();
  });

  it("uses the design's words for each card", () => {
    setup();
    expect(screen.getByText("Recommended for tuition")).toBeInTheDocument();
    expect(screen.getByText("May arrive short")).toBeInTheDocument();
    expect(screen.getByText("Highest short-payment risk")).toBeInTheDocument();
    expect(screen.getByText("sender pays all")).toBeInTheDocument();
    expect(screen.getByText(/so the university may receive less/)).toBeInTheDocument();
  });

  it("stops calling OUR recommended for tuition when the purpose is living costs", () => {
    setup("LIVING");
    expect(screen.queryByText("Recommended for tuition")).toBeNull();
    expect(screen.getByText("Lowest short-payment risk")).toBeInTheDocument();
  });

  it("chooses a card by click and by the arrow keys", async () => {
    const onChange = setup();
    await userEvent.click(screen.getByRole("radio", { name: /SHA/ }));
    expect(onChange).toHaveBeenLastCalledWith("SHA");
    screen.getByRole("radio", { name: /OUR/ }).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(onChange).toHaveBeenLastCalledWith("SHA");
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
