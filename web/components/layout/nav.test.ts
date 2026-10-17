import { describe, expect, it } from "vitest";

import { NAV, isActive, trailFor } from "@/components/layout/nav";

describe("nav", () => {
  it("lists every screen once, with a trailing slash except the dashboard", () => {
    const hrefs = NAV.map((item) => item.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs.filter((href) => href !== "/").every((href) => href.endsWith("/"))).toBe(true);
  });

  it("keeps the same role access as the screens", () => {
    const labels = (role: string) =>
      NAV.filter((item) => item.roles.includes(role)).map((item) => item.label);
    expect(labels("admin")).not.toContain("Compare");
    expect(labels("admin")).not.toContain("Recipients");
    expect(labels("admin")).not.toContain("Student guide");
    expect(labels("admin")).toContain("Bank review");
    expect(labels("parent")).not.toContain("Bank review");
    expect(labels("student")).not.toContain("Bank review");
    expect(labels("student")).toContain("Student guide");
    expect(labels("student")).not.toContain("Audit log");
    expect(labels("parent")).toEqual(
      expect.arrayContaining(["Compare", "Recipients", "Audit log"]),
    );
  });

  it("marks a screen active with or without the trailing slash, and for its sub-pages", () => {
    expect(isActive("/payments", "/payments/")).toBe(true);
    expect(isActive("/payments/view/", "/payments/")).toBe(true);
    expect(isActive("/paymentsx/", "/payments/")).toBe(false);
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/compare/", "/")).toBe(false);
  });

  it("builds the breadcrumb trail", () => {
    expect(trailFor("/")).toEqual(["Dashboard"]);
    expect(trailFor("/compare/")).toEqual(["Compare"]);
    expect(trailFor("/payments/")).toEqual(["Payments"]);
    expect(trailFor("/guide/")).toEqual(["Student guide"]);
    expect(trailFor("/payments/view/")).toEqual(["Payments", "Payment"]);
    expect(trailFor("/payments/report/")).toEqual(["Payments", "Compliance report"]);
    expect(trailFor("/nowhere/")).toEqual(["StudyRoute"]);
  });
});
