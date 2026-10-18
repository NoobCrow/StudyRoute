import { describe, expect, it } from "vitest";

import {
  DEFAULT_GUIDE_PARAMS,
  readGuideParams,
  writeGuideParams,
  type GuideParams,
} from "@/lib/schemas/guide-params";

const read = (query: string) => readGuideParams(new URLSearchParams(query));

describe("guide params", () => {
  it("opens the budget tab with a sensible budget when the address has nothing", () => {
    expect(read("")).toEqual(DEFAULT_GUIDE_PARAMS);
    expect(DEFAULT_GUIDE_PARAMS).toMatchObject({ tab: "budget", budget: "200000", arrival: "GB" });
  });

  it("reads every value from a shared link", () => {
    expect(read("tab=arrival&budget=150000&housing=studio&country=de&arrival=ca")).toEqual({
      tab: "arrival",
      budget: "150000",
      housing: "studio",
      country: "DE",
      arrival: "CA",
    });
  });

  it("takes thousands separators out of a budget and keeps two decimals at most", () => {
    expect(read("budget=1,50,000").budget).toBe("150000");
    expect(read("budget=90000.5").budget).toBe("90000.5");
    expect(read("budget=90000.555").budget).toBe(DEFAULT_GUIDE_PARAMS.budget);
  });

  it("treats an empty budget as 'no budget', not as the default", () => {
    expect(read("budget=").budget).toBe("");
    expect(writeGuideParams({ ...DEFAULT_GUIDE_PARAMS, budget: "" })).toBe("budget=");
  });

  it("falls back to the default for each bad value on its own", () => {
    const bad = read("tab=other&budget=abc&housing=castle&country=GBR&arrival=1x&budget2=1");
    expect(bad).toEqual(DEFAULT_GUIDE_PARAMS);
    expect(read("tab=arrival&housing=castle")).toMatchObject({ tab: "arrival", housing: "shared" });
  });

  it("refuses a budget that is too long to be a month's money", () => {
    expect(read("budget=12345678901").budget).toBe(DEFAULT_GUIDE_PARAMS.budget);
  });

  it("writes only what differs from the defaults, so the plain page has no query", () => {
    expect(writeGuideParams(DEFAULT_GUIDE_PARAMS)).toBe("");
    const changed: GuideParams = { ...DEFAULT_GUIDE_PARAMS, tab: "arrival", arrival: "DE" };
    expect(writeGuideParams(changed)).toBe("tab=arrival&arrival=DE");
  });

  it("round-trips any valid view", () => {
    const view: GuideParams = {
      tab: "budget",
      budget: "175000.5",
      housing: "studio",
      country: "AU",
      arrival: "MY",
    };
    expect(read(writeGuideParams(view))).toEqual(view);
  });
});
