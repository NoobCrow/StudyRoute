// After `next build` (static export): hash every inline <script> in out/**/*.html and write the
// nginx security headers for this app. The policy is the project's own (web/security_headers.base.conf)
// with one change: script-src lists the hashes of the exported inline bootstrap scripts, so
// 'unsafe-inline' is never needed. style-src stays 'self' (the app sets no inline style attributes).
//
//   node scripts/csp-hashes.mjs            writes web/security_headers.conf
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(WEB, "out");
const BASE = path.join(WEB, "security_headers.base.conf");
const TARGET = path.join(WEB, "security_headers.conf");

function* htmlFiles(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* htmlFiles(full);
    else if (entry.name.endsWith(".html")) yield full;
  }
}

const INLINE = /<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/g;

export function inlineScripts(html) {
  const found = [];
  for (const match of html.matchAll(INLINE)) {
    const attributes = match[1] ?? "";
    if (/type\s*=\s*["']?(?:application\/(?:ld\+)?json|importmap)/i.test(attributes)) continue; // data, never run
    found.push(match[2] ?? "");
  }
  return found;
}

export function sha256Source(text) {
  return `'sha256-${crypto.createHash("sha256").update(text, "utf8").digest("base64")}'`;
}

export function buildHeaders(baseConf, hashes) {
  const lines = baseConf
    .split("\n")
    .map((line) =>
      line.includes("Content-Security-Policy")
        ? line.replace("script-src 'self'", `script-src 'self' ${hashes.join(" ")}`.trimEnd())
        : line,
    );
  return lines.join("\n");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!fs.existsSync(OUT)) throw new Error("Run `next build` first: web/out does not exist.");
  const hashes = new Set();
  let scripts = 0;
  for (const file of htmlFiles(OUT)) {
    for (const body of inlineScripts(fs.readFileSync(file, "utf8"))) {
      hashes.add(sha256Source(body));
      scripts += 1;
    }
  }
  const sorted = [...hashes].sort();
  fs.writeFileSync(TARGET, buildHeaders(fs.readFileSync(BASE, "utf8"), sorted), "utf8");
  fs.writeFileSync(
    path.join(OUT, "csp-hashes.json"),
    JSON.stringify({ hashes: sorted }, null, 2) + "\n",
  );
  console.log(
    `CSP: ${scripts} inline scripts, ${sorted.length} distinct hashes -> web/security_headers.conf`,
  );
}
