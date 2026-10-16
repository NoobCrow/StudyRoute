// Signs in and visits every screen of the running app, reporting console errors and page errors.
//   node scripts/tour.mjs http://localhost:3000 <screenshot-folder> [who] [width]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(new URL("../../frontend/package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [base, folder, who = "parent", widthArg = "1440"] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
if (folder) fs.mkdirSync(folder, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
});
const page = await (await browser.createBrowserContext()).newPage();
await page.setViewport({ width: Number(widthArg), height: 1000 });
let errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => {
  if (r.failure()?.errorText !== "net::ERR_ABORTED")
    errors.push(`request failed: ${r.url()} ${r.failure()?.errorText}`);
});

await page.goto(`${base}/login/`, { waitUntil: "networkidle0" });
await page.type('input[type="email"]', `${who}@demo.studyroute.test`);
await page.type('input[type="password"]', "Sandbox#2026");
await page.click('button[type="submit"]');
await page.waitForSelector("main#main", { timeout: 20000 });
await sleep(1500);

const ROUTES = [
  "/",
  "/compare/",
  "/payments/",
  "/recipients/",
  "/documents/",
  "/audit/",
  "/rules/",
  "/bank/",
  "/escrow/",
  "/sandbox/",
];
let bad = 0;
for (const href of ROUTES) {
  await sleep(Number(process.env.TOUR_PAUSE ?? 0)); // the sign-in endpoints allow ten requests a minute
  errors = [];
  // A full page load: the session comes back from the refresh token, like a person pressing reload.
  await page.goto(`${base}${href}`, { waitUntil: "networkidle0" });
  await page.waitForSelector("main#main", { timeout: 20000 }).catch(() => undefined);
  await sleep(2500);
  const heading = await page
    .$eval("main#main h1", (el) => el.textContent)
    .catch(() => "(no h1: maybe not allowed for this role)");
  const horizontal = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  if (folder)
    await page.screenshot({
      path: path.join(folder, `${href.replace(/\//g, "") || "dashboard"}.png`),
      fullPage: true,
    });
  const status = errors.length === 0 && !horizontal ? "PASS" : "FAIL";
  if (status === "FAIL") bad += 1;
  console.log(
    `${status}  ${href.padEnd(14)} ${heading}${horizontal ? "  (horizontal scroll)" : ""}`,
  );
  for (const e of errors.slice(0, 4)) console.log(`      ${e.slice(0, 200)}`);
}
await browser.close();
process.exit(bad === 0 ? 0 : 1);
