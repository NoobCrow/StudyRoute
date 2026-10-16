import { describe, expect, it } from "vitest";

import { buildStrip, describeDay, stripStart, type StripDates } from "./calendar-strip";

/** The design's own example: due Fri 30 Oct, today Fri 16 Oct, UK, after the 15:00 cut-off. */
const DESIGN: StripDates = {
  today: "2026-10-16",
  earliest: "2026-10-19",
  recommended: "2026-10-21",
  latest: "2026-10-22",
  due: "2026-10-30",
};

describe("the deadline strip (layout only: every date comes from the engine)", () => {
  it("shows fifteen days that end on the due date when it is fifteen days away", () => {
    const days = buildStrip(DESIGN);
    expect(days).toHaveLength(15);
    expect(days[0]?.iso).toBe("2026-10-16");
    expect(days[14]?.iso).toBe("2026-10-30");
  });

  it("puts each marker on the right day and nowhere else", () => {
    const marked = Object.fromEntries(
      buildStrip(DESIGN)
        .filter((d) => d.markers.length > 0)
        .map((d) => [d.iso, d.markers]),
    );
    expect(marked).toEqual({
      "2026-10-16": ["today"],
      "2026-10-19": ["earliest"],
      "2026-10-21": ["recommended"],
      "2026-10-22": ["latest"],
      "2026-10-30": ["due"],
    });
  });

  it("starts today when the due date is near, and ends on the due date when it is far", () => {
    expect(stripStart("2026-10-16", "2026-10-20")).toBe("2026-10-16");
    expect(stripStart("2026-10-16", "2026-12-31")).toBe("2026-12-17");
    expect(buildStrip({ ...DESIGN, due: "2026-12-31" }).at(-1)?.iso).toBe("2026-12-31");
  });

  it("lets two markers share a day", () => {
    const days = buildStrip({ ...DESIGN, earliest: "2026-10-16" });
    expect(days[0]?.markers).toEqual(["today", "earliest"]);
  });

  it("labels the weekday with one letter and the day with its number", () => {
    const first = buildStrip(DESIGN)[0];
    expect(first).toMatchObject({ weekday: "F", day: 16 });
  });

  it("describes a day for a screen reader", () => {
    const days = buildStrip(DESIGN);
    expect(describeDay(days[5] as (typeof days)[number])).toBe("Wed 21 Oct: Recommended");
    expect(describeDay(days[1] as (typeof days)[number])).toBe("Sat 17 Oct");
  });
});
