import { describe, expect, it } from "vitest";

import { addDaysIso, clock, formatDate, secondsUntil, shortHash } from "./format";
import { parseMajorToMinor } from "./money";

describe("parseMajorToMinor", () => {
  it.each([
    ["10000", 1_000_000],
    ["10,000.50", 1_000_050],
    ["0.05", 5],
    ["  1 234.5 ", 123_450],
    ["19.99", 1999],
    ["0.1", 10],
  ])("turns %s into %i minor units without floating point", (input, minor) => {
    expect(parseMajorToMinor(input)).toEqual({ ok: true, minor });
  });

  it.each(["", "abc", "1.234", "-5", "1e5", "0", "0.00", "12.", ".5", "1,2,3.456"])(
    "refuses %j",
    (input) => {
      expect(parseMajorToMinor(input).ok).toBe(false);
    },
  );

  it("never goes through binary floats (19.99 stays 1999)", () => {
    const result = parseMajorToMinor("1000000.07");
    expect(result).toEqual({ ok: true, minor: 100_000_007 });
  });

  it("refuses absurdly large amounts", () => {
    expect(parseMajorToMinor("999999999999").ok).toBe(false);
  });
});

describe("format helpers", () => {
  it("formats dates and hashes for display only", () => {
    expect(formatDate("2026-10-28")).toBe("Wed, 28 Oct 2026");
    expect(formatDate(null)).toBe("-");
    expect(shortHash("sha256:" + "a".repeat(64))).toBe("aaaaaaaaaa...aaaa");
  });
  it("counts down in whole seconds and never below zero", () => {
    const now = Date.parse("2026-10-14T05:00:00Z");
    expect(secondsUntil("2026-10-14T05:04:30Z", now)).toBe(270);
    expect(secondsUntil("2026-10-14T04:00:00Z", now)).toBe(0);
    expect(clock(270)).toBe("4:30");
    expect(clock(5)).toBe("0:05");
  });
  it("adds days in UTC", () => {
    expect(addDaysIso(14, new Date("2026-10-14T23:30:00Z"))).toBe("2026-10-28");
  });
});

describe("formatMinorCompact", () => {
  it("lays out typed digits with thousands separators and keeps decimals only when they matter", async () => {
    const { formatMinorCompact } = await import("@/lib/money");
    expect(formatMinorCompact(1000000, 2)).toBe("10,000");
    expect(formatMinorCompact(1000050, 2)).toBe("10,000.50");
    expect(formatMinorCompact(5, 2)).toBe("0.05");
    expect(formatMinorCompact(1500000, 0)).toBe("1,500,000");
    expect(formatMinorCompact(123456789012, 2)).toBe("1,234,567,890.12");
    expect(formatMinorCompact(1234, 3)).toBe("1.234");
  });
});

describe("dhakaToday", () => {
  it("uses the Dhaka calendar day, which can be a day ahead of UTC", async () => {
    const { dhakaToday } = await import("@/lib/format");
    expect(dhakaToday(new Date("2026-10-15T20:30:00Z"))).toBe("2026-10-16");
    expect(dhakaToday(new Date("2026-10-15T17:59:00Z"))).toBe("2026-10-15");
  });
});
