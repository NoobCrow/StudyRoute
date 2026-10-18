import { describe, expect, it } from "vitest";

import { appHref } from "./links";

describe("appHref maps the API's screen paths to this app's routes", () => {
  it("adds the trailing slash every exported route has", () => {
    expect(appHref("/recipients")).toBe("/recipients/");
    expect(appHref("/documents")).toBe("/documents/");
    expect(appHref("/")).toBe("/");
  });

  it("keeps the query string", () => {
    expect(appHref("/compare?quote=qte_1&provider=prov_b")).toBe(
      "/compare/?quote=qte_1&provider=prov_b",
    );
  });

  it("moves a payment id into the query string", () => {
    expect(appHref("/payments/pay_9")).toBe("/payments/view/?id=pay_9");
    expect(appHref("/payments/pay_9/report")).toBe("/payments/report/?id=pay_9");
  });

  it("encodes an id so it cannot add parameters", () => {
    expect(appHref("/payments/a&b=c")).toBe("/payments/view/?id=a%26b%3Dc");
  });

  it("leaves the payments list alone", () => {
    expect(appHref("/payments")).toBe("/payments/");
  });
});
