// Test fixtures for the student guide: a few cities, one arrival list, and a fetch that answers both.
import { vi } from "vitest";

import type { ArrivalGuide, BudgetCity, Money, StudentBudget } from "@/lib/api/types";
import { corridor, problem } from "@/tests/fixtures";

export const money = (minor: number, currency: string, formatted: string): Money => ({
  amount_minor: minor,
  currency,
  formatted,
});

interface Place {
  city: string;
  country: string;
  country_name: string;
  currency: string;
  rent: string;
  total: string;
  bdt: number;
  bdtText: string;
  share: string;
  rate: string;
}
export const PLACES: Place[] = [
  {
    city: "Johor Bahru",
    country: "MY",
    country_name: "Malaysia",
    currency: "MYR",
    rent: "MYR 450.00",
    total: "MYR 1,570.00",
    bdt: 4_082_000,
    bdtText: "BDT 40,820.00",
    share: "28.7",
    rate: "26.000000",
  },
  {
    city: "Manchester",
    country: "GB",
    country_name: "United Kingdom",
    currency: "GBP",
    rent: "GBP 600.00",
    total: "GBP 1,195.00",
    bdt: 19_120_000,
    bdtText: "BDT 191,200.00",
    share: "50.2",
    rate: "160.000000",
  },
  {
    city: "London",
    country: "GB",
    country_name: "United Kingdom",
    currency: "GBP",
    rent: "GBP 850.00",
    total: "GBP 1,605.00",
    bdt: 25_680_000,
    bdtText: "BDT 256,800.00",
    share: "53.0",
    rate: "160.000000",
  },
];

export function bdt(minor: number): Money {
  const whole = Math.trunc(minor / 100)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return money(minor, "BDT", `BDT ${whole}.${String(minor % 100).padStart(2, "0")}`);
}

function row(place: Place, budgetMinor: number | null): BudgetCity {
  const fits = budgetMinor === null ? null : place.bdt <= budgetMinor;
  return {
    country: place.country,
    country_name: place.country_name,
    city: place.city,
    currency: place.currency,
    housing: "shared",
    lines: [
      { key: "rent", label: "Rent", ...money(0, place.currency, place.rent) },
      {
        key: "food",
        label: "Food and groceries",
        ...money(0, place.currency, `${place.currency} 240.00`),
      },
    ],
    total: money(0, place.currency, place.total),
    rent_share_pct: place.share,
    rate_bdt_per_unit: place.rate,
    total_bdt: money(place.bdt, "BDT", place.bdtText),
    rent_bdt: bdt(place.bdt / 2),
    fits,
    spare_bdt: fits ? bdt(budgetMinor! - place.bdt) : null,
    gap_bdt: fits === false ? bdt(place.bdt - budgetMinor!) : null,
  };
}

export function budgetBody(url: URL): StudentBudget {
  const housing = url.searchParams.get("housing") === "studio" ? "studio" : "shared";
  const raw = url.searchParams.get("budget_bdt_minor");
  const budgetMinor = raw === null ? null : Number(raw);
  const country = url.searchParams.get("country");
  const places = PLACES.filter((p) => !country || p.country === country);
  const items = places
    .map((p) => row(p, budgetMinor))
    .map((r) => ({ ...r, housing }) as BudgetCity);
  return {
    housing,
    housing_label: housing === "shared" ? "A room in a shared flat" : "Your own studio",
    budget: budgetMinor === null ? null : bdt(budgetMinor),
    countries: [
      { country: "GB", name: "United Kingdom", currency: "GBP", cities: 2 },
      { country: "MY", name: "Malaysia", currency: "MYR", cities: 1 },
    ],
    items,
    summary: {
      cities: items.length,
      fitting: budgetMinor === null ? null : items.filter((r) => r.fits).length,
      cheapest: items[0]
        ? {
            country: items[0].country,
            city: items[0].city,
            total: items[0].total,
            total_bdt: items[0].total_bdt,
          }
        : null,
      dearest: null,
    },
    source: {
      verified: false,
      badge: "NOT_VERIFIED",
      source_url: "https://example.org/replace-with-cost-of-living-source",
      last_checked: "2026-10-17",
      note: "Invented.",
    },
    synthetic: true,
    disclaimer:
      "Invented figures for the sandbox, not a survey. Compare them with your university's own estimate. Indicative. Confirm with your AD bank.",
  };
}

export function arrivalBody(url: URL): ArrivalGuide {
  const country = url.searchParams.get("country") ?? "GB";
  const general = country === "FR";
  return {
    country,
    country_name: general ? "France" : "United Kingdom",
    general,
    stages: [
      {
        key: "before",
        label: "Before you fly",
        items: [
          {
            key: "accommodation",
            label: "Book a place to live before you fly",
            hint: "Use the halls.",
          },
        ],
      },
      {
        key: "first_week",
        label: "In your first week",
        items: [
          {
            key: "student_account",
            label: "Open a student bank account",
            hint: "Take your passport.",
          },
        ],
      },
      {
        key: "first_month",
        label: "In your first month",
        items: [
          { key: "work_rules", label: "Know how much you may work", hint: "Check the visa page." },
          {
            key: "gb_doctor",
            label: "Register with a local doctor (GP)",
            hint: "Ask your university.",
          },
        ],
      },
    ],
    item_count: 4,
    verified: false,
    badge: "NOT_VERIFIED",
    source_url: "https://example.org/replace-with-official-student-guidance",
    last_checked: "2026-10-17",
    note: "Indicative. Confirm with your university.",
    indicative: "Indicative. Confirm with your AD bank.",
  };
}

/** Answers the three paths the screen reads, and remembers every address asked for. */
export function mockGuideApi(options: { budgetFails?: boolean } = {}) {
  const asked: URL[] = [];
  let budgetCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    asked.push(url);
    const path = url.pathname.replace("/api/v1", "");
    const ok = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    if (path === "/corridors") {
      return ok({
        items: [corridor(), corridor({ country: "FR", name: "France", currency: "EUR" })],
        providers: [],
      });
    }
    if (path === "/planner/student-budget") {
      budgetCalls += 1;
      if (options.budgetFails && budgetCalls === 1)
        return problem(500, "BROKEN", "The figures are not available.");
      return ok(budgetBody(url));
    }
    if (path === "/planner/arrival-guide") return ok(arrivalBody(url));
    return problem(500, "NOT_MOCKED", path);
  });
  vi.stubGlobal("fetch", fetchMock);
  const budgetAsks = () => asked.filter((u) => u.pathname.endsWith("/planner/student-budget"));
  return { budgetAsks, asked };
}
