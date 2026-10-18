import { describe, expect, it } from "vitest";

import type { ChecklistItem } from "@/lib/api/types";
import {
  checklistCounts,
  documentKindLabel,
  fileCount,
  filterChecklist,
  readiness,
  sampleFilename,
} from "@/lib/domain/documents";

const item = (key: string, provided: boolean): ChecklistItem => ({
  key,
  label: key,
  hint: "",
  provided,
});

const NINE = Array.from({ length: 9 }, (_, i) => item(`doc_${i}`, false));

describe("readiness", () => {
  it("is 0 of 9 and 0% when nothing is in", () => {
    expect(readiness(NINE)).toEqual({ ready: 0, total: 9, percent: 0 });
  });

  it("rounds to a whole percent", () => {
    const some = NINE.map((entry, i) => ({ ...entry, provided: i < 3 }));
    expect(readiness(some)).toEqual({ ready: 3, total: 9, percent: 33 });
    expect(readiness(NINE.map((entry, i) => ({ ...entry, provided: i < 2 })))).toMatchObject({
      percent: 22,
    });
    expect(readiness(NINE.map((entry) => ({ ...entry, provided: true })))).toMatchObject({
      ready: 9,
      percent: 100,
    });
  });

  it("is 0% for an empty list, not a division by zero", () => {
    expect(readiness([])).toEqual({ ready: 0, total: 0, percent: 0 });
  });
});

describe("checklist tabs", () => {
  const mixed = [item("a", true), item("b", false), item("c", false), item("d", true)];

  it("counts all, missing and ready", () => {
    expect(checklistCounts(mixed)).toEqual({ all: 4, missing: 2, ready: 2 });
    expect(checklistCounts([])).toEqual({ all: 0, missing: 0, ready: 0 });
  });

  it("filters a copy and keeps the order", () => {
    expect(filterChecklist(mixed, "all").map((i) => i.key)).toEqual(["a", "b", "c", "d"]);
    expect(filterChecklist(mixed, "missing").map((i) => i.key)).toEqual(["b", "c"]);
    expect(filterChecklist(mixed, "ready").map((i) => i.key)).toEqual(["a", "d"]);
    expect(filterChecklist(mixed, "all")).not.toBe(mixed);
  });
});

describe("names", () => {
  it("writes a document type as words and suggests a mock file name", () => {
    expect(documentKindLabel("source_of_funds")).toBe("source of funds");
    expect(sampleFilename("offer_letter")).toBe("offer-letter-mock.txt");
    expect(sampleFilename("ad_bank_form")).toBe("ad-bank-form-mock.txt");
  });

  it("counts files in the singular and the plural", () => {
    expect(fileCount(0)).toBe("0 files");
    expect(fileCount(1)).toBe("1 file");
    expect(fileCount(12)).toBe("12 files");
  });
});
