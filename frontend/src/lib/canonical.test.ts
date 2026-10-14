import { describe, expect, it } from "vitest";

import { canonicalJson, reportIsIntact, sha256Ref } from "./canonical";

// Computed by the backend's own hash_object() (app.core.crypto) for the same value.
const VALUE = {
  b: 1,
  a: ["x", { d: null, c: true, e: 0 }],
  name: "Provider é ü বাংলা",
  quote: 'say "hi"\n',
  nested: { z: [], y: {} },
};
const BACKEND_CANONICAL =
  '{"a":["x",{"c":true,"d":null,"e":0}],"b":1,"name":"Provider é ü বাংলা","nested":{"y":{},"z":[]},"quote":"say \\"hi\\"\\n"}';
const BACKEND_HASH = "sha256:5154559bf5deda7cd2b5e51aa7fecc65135cd9094faddfe802023003d29591e3";

describe("canonical JSON and the report hash", () => {
  it("produces exactly the bytes the backend hashes", () => {
    expect(canonicalJson(VALUE)).toBe(BACKEND_CANONICAL);
  });

  it("produces exactly the hash the backend computes, Bengali text included", async () => {
    expect(await sha256Ref(canonicalJson(VALUE))).toBe(BACKEND_HASH);
  });

  it("knows the standard SHA-256 test vector", async () => {
    expect(await sha256Ref("abc")).toBe(
      "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  it("accepts an untouched report and rejects an edited copy", async () => {
    const report = { ...VALUE, report_hash: BACKEND_HASH };
    expect(await reportIsIntact(report)).toBe(true);
    expect(await reportIsIntact({ ...report, b: 2 })).toBe(false);
    expect(await reportIsIntact({ ...report, report_hash: "sha256:00" })).toBe(false);
  });
});
