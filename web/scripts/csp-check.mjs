// Loads pages of the static export in real Chrome under the generated production CSP and fails on
// any violation, console error or failed request.
//   node ../scripts/security/prod_like_server.mjs 8091 8000 &   (serves web/out)
//   node scripts/csp-check.mjs http://127.0.0.1:8091 / /compare/
import { createRequire } from "node:module";

const require = createRequire(new URL("../package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [base, ...paths] = process.argv.slice(2);
if (!base) throw new Error("Usage: node scripts/csp-check.mjs <base-url> [path ...]");

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
});
let failures = 0;
for (const route of paths.length ? paths : ["/"]) {
  const page = await browser.newPage();
  const problems = [];
  await page.evaluateOnNewDocument(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      console.error(
        `CSP violation: ${e.violatedDirective} blocked ${e.blockedURI || "inline"} ${(e.sample || "").slice(0, 60)}`,
      );
    });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(msg.text());
  });
  page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
  page.on("requestfailed", (request) => problems.push(`request failed: ${request.url()}`));
  await page.goto(`${base}${route}`, { waitUntil: "networkidle0" });
  const text = await page.evaluate(() => document.body.innerText.trim().slice(0, 80));
  console.log(
    `${problems.length === 0 ? "PASS" : "FAIL"}  ${route}  ("${text.replace(/\n/g, " | ")}")`,
  );
  for (const problem of problems) console.log(`      ${problem}`);
  failures += problems.length;
  await page.close();
}
await browser.close();
process.exit(failures === 0 ? 0 : 1);
