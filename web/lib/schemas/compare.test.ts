import { describe, expect, it } from "vitest";

import {
  amountToMinor,
  quoteRequestSchema,
  readCompareParams,
  writeCompareParams,
  type CompareValues,
} from "@/lib/schemas/compare";

const TODAY = "2026-10-16";
const VALID: CompareValues = {
  country: "GB",
  amount: "10000",
  purpose: "TUITION",
  charge: "OUR",
  dueDate: "2026-10-30",
  recipientId: "",
};

function problems(values: Partial<CompareValues>, exponent = 2): string[] {
  const result = quoteRequestSchema(exponent, TODAY).safeParse({ ...VALID, ...values });
  return result.success ? [] : result.error.issues.map((issue) => issue.message);
}

describe("quoteRequestSchema", () => {
  it("accepts the default request", () => {
    expect(problems({})).toEqual([]);
  });

  it("takes a recipient as optional", () => {
    expect(problems({ recipientId: "" })).toEqual([]);
    expect(problems({ recipientId: "rcp_1" })).toEqual([]);
  });

  it("rejects an amount that is not a number, zero, or has too many decimals", () => {
    expect(problems({ amount: "ten" })[0]).toContain("Amount: Use digits only");
    expect(problems({ amount: "" })[0]).toContain("Amount: Enter an amount");
    expect(problems({ amount: "0" })[0]).toContain("greater than zero");
    expect(problems({ amount: "10.505" })[0]).toContain("at most 2 decimal places");
  });

  it("follows the currency's decimals", () => {
    expect(problems({ amount: "1500000" }, 0)).toEqual([]);
    expect(problems({ amount: "1500000.5" }, 0)[0]).toContain("no decimals");
    expect(problems({ amount: "10.505" }, 3)).toEqual([]);
  });

  it("bounds the amount", () => {
    expect(problems({ amount: "99999999999999" })[0]).toContain("Amount");
    expect(problems({ amount: "10,000.50" })).toEqual([]);
  });

  it("wants a due date that is real and not in the past", () => {
    expect(problems({ dueDate: "" })[0]).toBe("Choose the date the university needs the money.");
    expect(problems({ dueDate: "2026-02-31" })).toContain("Choose a valid date.");
    expect(problems({ dueDate: "2026-10-15" })).toEqual(["The due date cannot be in the past."]);
    expect(problems({ dueDate: TODAY })).toEqual([]);
  });

  it("rejects a purpose, charge code or country it does not know", () => {
    expect(problems({ purpose: "GIFT" as never }).length).toBeGreaterThan(0);
    expect(problems({ charge: "ABC" as never }).length).toBeGreaterThan(0);
    expect(problems({ country: "gb" })[0]).toBe("Choose a destination country.");
  });
});

describe("amountToMinor", () => {
  it("turns typed text into integer minor units without floating point", () => {
    expect(amountToMinor("10,000.10", 2)).toBe(1000010);
    expect(amountToMinor("0.30", 2)).toBe(30);
    expect(amountToMinor("1500000", 0)).toBe(1500000);
    expect(amountToMinor("abc", 2)).toBeNull();
  });
});

describe("compare URL parameters", () => {
  it("reads a shared comparison", () => {
    const search = new URLSearchParams(
      "destination=JP&amount=1500000&purpose=living&chargeCode=SHA&dueDate=2026-11-20&recipientId=rcp_9",
    );
    expect(readCompareParams(search, VALID)).toEqual({
      country: "JP",
      amount: "1500000",
      purpose: "LIVING",
      charge: "SHA",
      dueDate: "2026-11-20",
      recipientId: "rcp_9",
    });
  });

  it("falls back to the defaults, one parameter at a time, when a value is bad or missing", () => {
    const search = new URLSearchParams(
      "destination=United&amount=<script>&purpose=gift&chargeCode=OUR&dueDate=soon&recipientId=a b",
    );
    expect(readCompareParams(search, VALID)).toEqual({ ...VALID, charge: "OUR" });
    expect(readCompareParams(new URLSearchParams(""), VALID)).toEqual(VALID);
  });

  it("accepts lower-case codes", () => {
    const search = new URLSearchParams("destination=gb&chargeCode=ben");
    expect(readCompareParams(search, VALID)).toMatchObject({ country: "GB", charge: "BEN" });
  });

  it("writes only the parameters that are valid, and reads back what it wrote", () => {
    const text = writeCompareParams({ ...VALID, amount: "10,000.50", recipientId: "rcp_1" });
    expect(text).toBe(
      "destination=GB&amount=10000.50&purpose=TUITION&chargeCode=OUR&dueDate=2026-10-30&recipientId=rcp_1",
    );
    expect(readCompareParams(new URLSearchParams(text), VALID)).toMatchObject({
      amount: "10000.50",
      recipientId: "rcp_1",
    });
    expect(writeCompareParams({ ...VALID, amount: "ten", dueDate: "" })).toBe(
      "destination=GB&purpose=TUITION&chargeCode=OUR",
    );
  });

  it("never writes an account number or any other free text", () => {
    expect(writeCompareParams({ ...VALID, recipientId: "GB08 EXMP 1234" })).not.toContain("GB08");
  });
});
