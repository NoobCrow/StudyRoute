// Compiles contracts/src/*.sol with the solc-js that npm installs (no compiler download) and writes
// one artifact per contract into backend/app/chain/artifacts/. The artifacts are committed, so the
// backend never needs Node or a compiler at run time. A Python test checks that every artifact
// still matches its source file (by SHA-256), so a changed contract cannot ship un-rebuilt.
//
//   cd contracts && npm ci && npm run build

import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const solc = require("solc");
const { keccak256 } = require("js-sha3");

const here = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.join(here, "src");
const outDir = path.join(here, "..", "backend", "app", "chain", "artifacts");
const EVM_VERSION = "paris"; // no PUSH0, so it runs on older EVM-compatible chains too

const files = fs.readdirSync(srcDir).filter((name) => name.endsWith(".sol")).sort();
const sources = Object.fromEntries(files.map((f) => [f, { content: fs.readFileSync(path.join(srcDir, f), "utf8") }]));

const input = {
  language: "Solidity",
  sources,
  settings: {
    evmVersion: EVM_VERSION,
    optimizer: { enabled: true, runs: 200 },
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object", "evm.methodIdentifiers"] } },
  },
};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
const problems = (output.errors ?? []).filter((e) => e.severity === "error");
for (const e of output.errors ?? []) console.error(`${e.severity}: ${e.formattedMessage}`);
if (problems.length > 0) process.exit(1);

const typeOf = (p) => p.type; // only elementary types are used, so the type string is the canonical one
const signature = (item) => `${item.name}(${item.inputs.map(typeOf).join(",")})`;

fs.mkdirSync(outDir, { recursive: true });
for (const file of files) {
  const [name] = Object.keys(output.contracts[file]).filter((c) => c !== "IDeposit");
  const compiled = output.contracts[file][name];
  const events = Object.fromEntries(
    compiled.abi.filter((i) => i.type === "event").map((i) => [signature(i), keccak256(signature(i))]),
  );
  const artifact = {
    contract: name,
    solc: solc.version(),
    evmVersion: EVM_VERSION,
    sourceFile: `contracts/src/${file}`,
    sourceSha256: createHash("sha256").update(sources[file].content).digest("hex"),
    abi: compiled.abi,
    bytecode: compiled.evm.bytecode.object,
    selectors: compiled.evm.methodIdentifiers,
    events,
  };
  fs.writeFileSync(path.join(outDir, `${name}.json`), JSON.stringify(artifact, null, 1) + "\n");
  console.log(`${name}: ${artifact.bytecode.length / 2} bytes, ${Object.keys(artifact.selectors).length} functions, ${Object.keys(events).length} events`);
}
