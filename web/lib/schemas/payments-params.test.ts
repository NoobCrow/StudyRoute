import { describe, expect, it } from "vitest";

import {
  DEFAULT_PAYMENTS_PARAMS,
  parseRange,
  rangeValue,
  readPaymentsParams,
  writePaymentsParams,
} from "@/lib/schemas/payments-params";

const read = (text: string) => readPaymentsParams(new URLSearchParams(text));

describe("readPaymentsParams", () => {
  it("opens the plain list with no parameters", () => {
    expect(read("")).toEqual(DEFAULT_PAYMENTS_PARAMS);
    expect(DEFAULT_PAYMENTS_PARAMS.range).toBe("30d");
  });

  it("reads a shared view", () => {
    expect(
      read(
        "status=completed&q=fees&currency=gbp&range=2026-10-01..2026-10-16&page=2&sort=amount&dir=asc",
      ),
    ).toEqual({
      status: "completed",
      q: "fees",
      currency: "GBP",
      range: "2026-10-01..2026-10-16",
      page: 2,
      sort: "amount",
      dir: "asc",
    });
  });

  it("falls back to the default of any parameter that is not valid, one at a time", () => {
    expect(
      read("status=cancelled&currency=pounds&range=yesterday&page=0&sort=password&dir=sideways"),
    ).toEqual(DEFAULT_PAYMENTS_PARAMS);
    expect(read("status=completed&page=abc")).toMatchObject({ status: "completed", page: 1 });
    expect(read("page=2.5").page).toBe(1);
    expect(read("range=2026-10-16..2026-10-01").range).toBe("30d");
    expect(read("range=2026-02-31..2026-03-01").range).toBe("30d");
  });

  it("keeps a search of any harmless text and cuts a very long one", () => {
    expect(read("q=%20INV-2026%20").q).toBe("INV-2026");
    expect(read(`q=${"x".repeat(200)}`).q).toBe("");
  });

  it("accepts the presets in any case", () => {
    for (const preset of ["7d", "30D", "YEAR", "all"]) {
      expect(read(`range=${preset}`).range).toBe(preset.toLowerCase());
    }
  });
});

describe("writePaymentsParams", () => {
  it("writes nothing for the plain list", () => {
    expect(writePaymentsParams(DEFAULT_PAYMENTS_PARAMS)).toBe("");
  });

  it("writes only what differs, and reads back what it wrote", () => {
    const view = {
      ...DEFAULT_PAYMENTS_PARAMS,
      status: "needs_attention" as const,
      q: "INV 7",
      currency: "JPY",
      range: "all",
      page: 3,
      sort: "reference" as const,
      dir: "asc" as const,
    };
    const text = writePaymentsParams(view);
    expect(text).toBe(
      "status=needs_attention&q=INV+7&currency=JPY&range=all&page=3&sort=reference&dir=asc",
    );
    expect(read(text)).toEqual(view);
    expect(writePaymentsParams({ ...DEFAULT_PAYMENTS_PARAMS, status: "completed" })).toBe(
      "status=completed",
    );
  });
});

describe("parseRange", () => {
  it("turns presets into days (Dhaka today), a custom range into itself, and nonsense into undefined", () => {
    expect(parseRange("30d", "2026-10-16")).toEqual({ from: "2026-09-17", to: "2026-10-16" });
    expect(parseRange("all", "2026-10-16")).toBeNull();
    expect(parseRange("2026-10-01..2026-10-16", "2026-10-16")).toEqual({
      from: "2026-10-01",
      to: "2026-10-16",
    });
    expect(parseRange("soon", "2026-10-16")).toBeUndefined();
    expect(rangeValue({ from: "2026-10-01", to: "2026-10-16" })).toBe("2026-10-01..2026-10-16");
  });
});
