// Signs in as a demo user and screenshots a route at a given width, to compare with the design.
//   node scripts/shot.mjs http://localhost:3000 out.png [width] [route] [who]
import { createRequire } from "node:module";

const require = createRequire(new URL("../../frontend/package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [base, out, widthArg, route = "/", who = "parent", theme = "light"] = process.argv.slice(2);
const width = Number(widthArg ?? 1440);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
});
const page = await (await browser.createBrowserContext()).newPage();
await page.setViewport({ width, height: 1000, deviceScaleFactor: 1 });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: theme }]);
await page.goto(`${base}/login/`, { waitUntil: "networkidle0" });
await page.waitForSelector('input[type="email"]');
await page.type('input[type="email"]', `${who}@demo.studyroute.test`);
await page.type('input[type="password"]', "Sandbox#2026");
await page.click('button[type="submit"]');
await page.waitForSelector("main#main", { timeout: 20000 });
if (route !== "/") {
  await page.evaluate((r) => document.querySelector(`a[href="${r}"]`)?.click(), route);
  await sleep(500);
}
await sleep(2500);
await page.screenshot({ path: out, fullPage: true });
console.log("saved", out, "errors:", errors.length);
for (const e of errors.slice(0, 8)) console.log("  ", e.slice(0, 220));
await browser.close();
