import { describe, expect, it } from "vitest";

import { corridor } from "@/tests/fixtures";
import {
  corridorForCurrency,
  currencyGroups,
  exponentFor,
  formDefaults,
  splitCorridors,
} from "./corridors";
import { parseMajorToMinor } from "./money";

const GB = corridor();
const DE = corridor({ country: "DE", name: "Germany", currency: "EUR", account_scheme: "IBAN" });
const JP = corridor({
  country: "JP",
  name: "Japan",
  currency: "JPY",
  account_scheme: "ACCOUNT",
  exponent: 0,
  featured: false,
  sample_amount: "2000000",
});
const KW = corridor({
  country: "KW",
  name: "Kuwait",
  currency: "KWD",
  account_scheme: "IBAN",
  exponent: 3,
  featured: false,
  sample_amount: "4000",
});
const FR = corridor({
  country: "FR",
  name: "France",
  currency: "EUR",
  account_scheme: "IBAN",
  featured: false,
});
const KP = corridor({
  country: "KP",
  name: "North Korea",
  currency: "KPW",
  account_scheme: "ACCOUNT",
  exponent: 0,
  featured: false,
  restricted: true,
  sample_amount: "200000000",
});
const ALL = [GB, DE, KW, JP, FR, KP];

describe("destination list helpers", () => {
  it("puts the featured countries in one group and the rest in another, each by name", () => {
    const { featured, others } = splitCorridors(ALL);
    expect(featured.map((c) => c.name)).toEqual(["Germany", "United Kingdom"]);
    expect(others.map((c) => c.name)).toEqual(["France", "Japan", "Kuwait", "North Korea"]);
  });

  it("groups currencies the same way and lists each one once", () => {
    expect(currencyGroups(ALL)).toEqual({
      featured: ["EUR", "GBP"],
      others: ["JPY", "KPW", "KWD"],
    });
  });

  it("finds the corridor behind a currency, preferring a featured one that is not restricted", () => {
    expect(corridorForCurrency(ALL, "EUR")?.country).toBe("DE");
    expect(corridorForCurrency(ALL, "KPW")?.country).toBe("KP");
    expect(corridorForCurrency(ALL, "ZZZ")).toBeUndefined();
  });

  it("reads decimals from the corridor and falls back to two", () => {
    expect(exponentFor(ALL, "JPY")).toBe(0);
    expect(exponentFor(ALL, "KWD")).toBe(3);
    expect(exponentFor(ALL, "GBP")).toBe(2);
    expect(exponentFor(ALL, "ZZZ")).toBe(2);
  });

  it("keeps the long-standing GBP defaults and scales the rest with the sample amount", () => {
    expect(formDefaults(GB)).toEqual({
      amount: "10000",
      runwayAmount: "5000",
      runwayMonthly: "1200",
      sendPlanMonthly: "1000",
    });
    expect(formDefaults(JP)).toEqual({
      amount: "2000000",
      runwayAmount: "1000000",
      runwayMonthly: "240000",
      sendPlanMonthly: "200000",
    });
    expect(formDefaults(undefined).amount).toBe("10000");
  });
});

describe("amounts in currencies with other decimals", () => {
  it("whole-unit currencies take no decimals", () => {
    expect(parseMajorToMinor("2,000,000", 0)).toEqual({ ok: true, minor: 2000000 });
    const refused = parseMajorToMinor("10.5", 0);
    expect(refused.ok).toBe(false);
    expect(refused.ok ? "" : refused.error).toMatch(/no decimals/);
  });

  it("three-decimal currencies keep three", () => {
    expect(parseMajorToMinor("1.5", 3)).toEqual({ ok: true, minor: 1500 });
    expect(parseMajorToMinor("1.2345", 3).ok).toBe(false);
  });

  it("two decimals stay the default", () => {
    expect(parseMajorToMinor("10,000.50")).toEqual({ ok: true, minor: 1000050 });
  });
});
