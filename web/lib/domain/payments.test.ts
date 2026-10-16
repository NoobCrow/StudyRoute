import { describe, expect, it } from "vitest";

import type { PaymentBrief, PaymentState } from "@/lib/api/types";
import {
  canCancel,
  currenciesOf,
  dhakaDay,
  filterPayments,
  pageNumbers,
  paginate,
  paymentsToCsv,
  rangeFor,
  sortPayments,
  statusCounts,
  statusOf,
  type PaymentFilters,
} from "@/lib/domain/payments";

function pay(id: string, over: Partial<PaymentBrief> = {}): PaymentBrief {
  return {
    payment_id: id,
    state: "QUOTED",
    target: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
    provider_id: "prov_b",
    provider_name: "Provider B (synthetic)",
    recipient_label: "University of Example (synthetic) GB** **** 4821",
    reference: `INV-${id}`,
    due_date: "2026-10-30",
    uetr: null,
    parent_pays: "BDT 1,625,300.00",
    created_at: "2026-10-14T09:31:00Z",
    updated_at: "2026-10-14T09:31:00Z",
    ...over,
  };
}

const NONE: PaymentFilters = { status: "all", q: "", currency: "", range: null };

const SAMPLE = [
  pay("1", { state: "QUOTED" }),
  pay("2", { state: "SETTLED", reference: "Fees-2026", created_at: "2026-10-10T20:00:00Z" }),
  pay("3", {
    state: "FAILED",
    target: { amount_minor: 150000000, currency: "JPY", formatted: "JPY 1,500,000" },
  }),
  pay("4", { state: "CANCELLED" }),
  pay("5", { state: "SUBMITTED", recipient_label: "Maple Street Student (synthetic)" }),
];

describe("statusOf and canCancel", () => {
  it("folds the nine states into the four words of the list", () => {
    const states: [PaymentState, string][] = [
      ["DRAFT", "in_progress"],
      ["QUOTED", "in_progress"],
      ["PENDING_APPROVAL", "in_progress"],
      ["APPROVED", "in_progress"],
      ["SUBMITTED", "in_progress"],
      ["SETTLED", "completed"],
      ["REJECTED", "needs_attention"],
      ["FAILED", "needs_attention"],
      ["CANCELLED", "cancelled"],
    ];
    for (const [state, status] of states) expect(statusOf(state)).toBe(status);
  });

  it("lets only the states the server allows be cancelled (not once the money is submitted)", () => {
    expect(canCancel("DRAFT")).toBe(true);
    expect(canCancel("QUOTED")).toBe(true);
    expect(canCancel("PENDING_APPROVAL")).toBe(true);
    expect(canCancel("APPROVED")).toBe(true);
    expect(canCancel("SUBMITTED")).toBe(false);
    expect(canCancel("SETTLED")).toBe(false);
    expect(canCancel("FAILED")).toBe(false);
    expect(canCancel("CANCELLED")).toBe(false);
  });
});

describe("statusCounts", () => {
  it("counts each tab, with cancelled payments only in All", () => {
    expect(statusCounts(SAMPLE)).toEqual({
      all: 5,
      in_progress: 2,
      completed: 1,
      needs_attention: 1,
    });
    expect(statusCounts([])).toEqual({ all: 0, in_progress: 0, completed: 0, needs_attention: 0 });
  });
});

describe("filterPayments", () => {
  it("filters by status tab", () => {
    expect(
      filterPayments(SAMPLE, { ...NONE, status: "completed" }).map((p) => p.payment_id),
    ).toEqual(["2"]);
    expect(
      filterPayments(SAMPLE, { ...NONE, status: "in_progress" }).map((p) => p.payment_id),
    ).toEqual(["1", "5"]);
    expect(filterPayments(SAMPLE, NONE)).toHaveLength(5);
  });

  it("searches reference and recipient, ignoring case and surrounding spaces", () => {
    expect(filterPayments(SAMPLE, { ...NONE, q: "  fees-2026 " }).map((p) => p.payment_id)).toEqual(
      ["2"],
    );
    expect(filterPayments(SAMPLE, { ...NONE, q: "MAPLE" }).map((p) => p.payment_id)).toEqual(["5"]);
    expect(filterPayments(SAMPLE, { ...NONE, q: "nothing like this" })).toEqual([]);
  });

  it("does not search the provider, the amount or the id", () => {
    expect(filterPayments(SAMPLE, { ...NONE, q: "provider b" })).toEqual([]);
    expect(filterPayments(SAMPLE, { ...NONE, q: "10,000" })).toEqual([]);
  });

  it("filters by currency", () => {
    expect(filterPayments(SAMPLE, { ...NONE, currency: "JPY" }).map((p) => p.payment_id)).toEqual([
      "3",
    ]);
    expect(currenciesOf(SAMPLE)).toEqual(["GBP", "JPY"]);
  });

  it("takes date ranges inclusively on the Dhaka calendar", () => {
    // 20:00 UTC on 10 Oct is 02:00 on 11 Oct in Dhaka.
    expect(dhakaDay("2026-10-10T20:00:00Z")).toBe("2026-10-11");
    const range = (from: string, to: string) =>
      filterPayments(SAMPLE, { ...NONE, range: { from, to } }).map((p) => p.payment_id);
    expect(range("2026-10-11", "2026-10-11")).toEqual(["2"]);
    expect(range("2026-10-10", "2026-10-10")).toEqual([]);
    expect(range("2026-10-14", "2026-10-14")).toEqual(["1", "3", "4", "5"]);
    expect(range("2026-10-11", "2026-10-14")).toHaveLength(5);
  });

  it("combines every filter", () => {
    const result = filterPayments(SAMPLE, {
      status: "in_progress",
      q: "inv",
      currency: "GBP",
      range: { from: "2026-10-01", to: "2026-10-31" },
    });
    expect(result.map((p) => p.payment_id)).toEqual(["1", "5"]);
  });
});

describe("rangeFor", () => {
  it("covers the last 7 and 30 days ending today, and this year", () => {
    expect(rangeFor("7d", "2026-10-16")).toEqual({ from: "2026-10-10", to: "2026-10-16" });
    expect(rangeFor("30d", "2026-10-16")).toEqual({ from: "2026-09-17", to: "2026-10-16" });
    expect(rangeFor("year", "2026-10-16")).toEqual({ from: "2026-01-01", to: "2026-10-16" });
    expect(rangeFor("all", "2026-10-16")).toBeNull();
  });

  it("steps over month and year ends", () => {
    expect(rangeFor("7d", "2026-01-03")).toEqual({ from: "2025-12-28", to: "2026-01-03" });
    expect(rangeFor("30d", "2026-03-01")?.from).toBe("2026-01-31");
  });
});

describe("sortPayments", () => {
  it("sorts by created, newest first, without touching the original", () => {
    const copy = [...SAMPLE];
    expect(sortPayments(SAMPLE, "created", "desc").map((p) => p.payment_id)).toEqual([
      "1",
      "3",
      "4",
      "5",
      "2",
    ]);
    expect(SAMPLE).toEqual(copy);
  });

  it("sorts text columns ignoring case, and reverses", () => {
    expect(sortPayments(SAMPLE, "reference", "asc").map((p) => p.reference)).toEqual([
      "Fees-2026",
      "INV-1",
      "INV-3",
      "INV-4",
      "INV-5",
    ]);
    expect(sortPayments(SAMPLE, "reference", "desc")[0]?.reference).toBe("INV-5");
  });

  it("groups amounts by currency before comparing the integers", () => {
    const mixed = [
      pay("a", { target: { amount_minor: 9000000, currency: "JPY", formatted: "x" } }),
      pay("b", { target: { amount_minor: 500, currency: "GBP", formatted: "x" } }),
      pay("c", { target: { amount_minor: 100, currency: "GBP", formatted: "x" } }),
    ];
    expect(sortPayments(mixed, "amount", "asc").map((p) => p.payment_id)).toEqual(["c", "b", "a"]);
  });

  it("keeps a stable order for equal values", () => {
    const ties = [pay("b"), pay("a"), pay("c")];
    expect(sortPayments(ties, "provider", "asc").map((p) => p.payment_id)).toEqual(["a", "b", "c"]);
    expect(sortPayments(ties, "provider", "desc").map((p) => p.payment_id)).toEqual([
      "a",
      "b",
      "c",
    ]);
  });
});

describe("paginate", () => {
  const items = Array.from({ length: 23 }, (_, i) => i + 1);

  it("slices a page and reports how many there are", () => {
    expect(paginate(items, 1, 10)).toEqual({
      items: items.slice(0, 10),
      page: 1,
      pages: 3,
      total: 23,
    });
    expect(paginate(items, 3, 10).items).toEqual([21, 22, 23]);
  });

  it("clamps a page that is too low, too high or not a number", () => {
    expect(paginate(items, 0, 10).page).toBe(1);
    expect(paginate(items, 99, 10).page).toBe(3);
    expect(paginate(items, Number.NaN, 10).page).toBe(1);
  });

  it("has one empty page for an empty list", () => {
    expect(paginate([], 1, 10)).toEqual({ items: [], page: 1, pages: 1, total: 0 });
  });
});

describe("paymentsToCsv", () => {
  it("writes a header and one line per payment, as the API formatted them", () => {
    const csv = paymentsToCsv([pay("1")]);
    const [head, line] = csv.trimEnd().split("\r\n");
    expect(head).toBe("Reference,Recipient,Beneficiary receives,Provider,Status,Created");
    expect(line).toBe(
      'INV-1,University of Example (synthetic) GB** **** 4821,"GBP 10,000.00",Provider B (synthetic),In progress,2026-10-14T09:31:00Z',
    );
  });

  it("quotes cells with commas, quotes or line breaks", () => {
    const csv = paymentsToCsv([pay("1", { reference: 'He said "hi", twice' })]);
    expect(csv).toContain('"He said ""hi"", twice"');
  });

  it("defuses spreadsheet formulas in what a person typed", () => {
    for (const evil of ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)"]) {
      const csv = paymentsToCsv([pay("1", { reference: evil })]);
      expect(
        csv.split("\r\n")[1]?.startsWith(`'${evil[0]}`) ||
          csv.split("\r\n")[1]?.startsWith(`"'${evil[0]}`),
      ).toBe(true);
    }
  });

  it("is just the header for no rows", () => {
    expect(paymentsToCsv([])).toBe(
      "Reference,Recipient,Beneficiary receives,Provider,Status,Created\r\n",
    );
  });
});

describe("pageNumbers", () => {
  it("lists every page when there are few", () => {
    expect(pageNumbers(1, 1)).toEqual([1]);
    expect(pageNumbers(2, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageNumbers(4, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("keeps the first, the last and the neighbours of the current page when there are many", () => {
    expect(pageNumbers(1, 20)).toEqual([1, 2, "gap", 20]);
    expect(pageNumbers(10, 20)).toEqual([1, "gap", 9, 10, 11, "gap", 20]);
    expect(pageNumbers(20, 20)).toEqual([1, "gap", 19, 20]);
    expect(pageNumbers(3, 20)).toEqual([1, 2, 3, 4, "gap", 20]);
  });
});
