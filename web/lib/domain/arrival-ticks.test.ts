import { describe, expect, it } from "vitest";

import { doneCount, readTicks, writeTicks } from "@/lib/domain/arrival-ticks";

function fakeStore(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

describe("arrival ticks", () => {
  it("remembers the ticked steps per country", () => {
    const store = fakeStore();
    writeTicks("GB", ["accommodation", "local_sim"], store);
    writeTicks("DE", ["de_register_address"], store);
    expect(readTicks("GB", store)).toEqual(["accommodation", "local_sim"]);
    expect(readTicks("DE", store)).toEqual(["de_register_address"]);
    expect(readTicks("CA", store)).toEqual([]);
  });

  it("forgets a country when its last tick is removed", () => {
    const store = fakeStore();
    writeTicks("GB", ["a"], store);
    writeTicks("GB", [], store);
    expect(store.data.size).toBe(0);
  });

  it("saves each step once", () => {
    const store = fakeStore();
    writeTicks("GB", ["a", "a", "b"], store);
    expect(readTicks("GB", store)).toEqual(["a", "b"]);
  });

  it("ignores saved text that is not a list of keys", () => {
    expect(readTicks("GB", fakeStore({ "studyroute.arrival.GB": "{not json" }))).toEqual([]);
    expect(readTicks("GB", fakeStore({ "studyroute.arrival.GB": '{"a":1}' }))).toEqual([]);
    expect(readTicks("GB", fakeStore({ "studyroute.arrival.GB": '["ok", 7, null]' }))).toEqual([
      "ok",
    ]);
  });

  it("never throws when storage is missing or refuses to work", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("full");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readTicks("GB", broken)).toEqual([]);
    expect(() => writeTicks("GB", ["a"], broken)).not.toThrow();
    expect(() => writeTicks("GB", ["a"], null)).not.toThrow();
    expect(readTicks("GB", null)).toEqual([]);
  });

  it("counts only ticks that are still steps of the guide", () => {
    expect(doneCount(["a", "b", "old"], ["a", "b", "c"])).toBe(2);
    expect(doneCount(["a", "a"], ["a"])).toBe(1);
    expect(doneCount([], ["a"])).toBe(0);
  });
});
