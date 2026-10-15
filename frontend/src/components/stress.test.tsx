import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { STRESS, mockApi, problem } from "../test/fixtures";
import { StressCard } from "./StressCard";

afterEach(() => vi.unstubAllGlobals());

describe("StressCard", () => {
  it("shows today and each what-if with the extra taka, all formatted by the server", async () => {
    const fetcher = mockApi({ "/quotes/qte_1/stress": STRESS });
    render(<StressCard quoteId="qte_1" providerId="prov_b" />);
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
    render(<StressCard quoteId="qte_1" providerId="prov_b" />);
    expect(await screen.findByText(/not a forecast/)).toBeInTheDocument();
    expect(screen.getByText(/Indicative\. Confirm with your AD bank\./)).toBeInTheDocument();
  });

  it("shows the problem instead of guessing when the server refuses", async () => {
    mockApi({ "/quotes/qte_1/stress": problem(404, "NOT_FOUND", "Quote not found.") });
    render(<StressCard quoteId="qte_1" providerId="prov_b" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Quote not found.");
  });
});
