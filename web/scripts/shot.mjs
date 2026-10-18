// Signs in as a demo user and screenshots a route at a given width, to compare with the design.
//   node scripts/shot.mjs http://localhost:3000 out.png [width] [route] [who] [theme] [action]
//   action "quotes": on /compare/, press Get quotes and wait for the results before the screenshot.
import { createRequire } from "node:module";

const require = createRequire(new URL("../package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [base, out, widthArg, route = "/", who = "parent", theme = "light", action = ""] =
  process.argv.slice(2);
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
  // On a narrow screen the menu is closed and its links are not in the page: load the route instead.
  const clicked = await page.evaluate((r) => {
    const link = document.querySelector(`a[href="${r}"]`);
    link?.click();
    return Boolean(link);
  }, route);
  if (clicked) await sleep(500);
  else await page.goto(`${base}${route}`, { waitUntil: "networkidle0" });
}
await sleep(2500);
if (action === "quotes") {
  await page.evaluate(() =>
    [...document.querySelectorAll("button")]
      .find((b) => b.textContent.trim() === "Get quotes")
      ?.click(),
  );
  await page.waitForSelector('[aria-label="Provider comparison table"]', { timeout: 20000 });
  await sleep(1500);
}
await page.screenshot({ path: out, fullPage: true });
console.log("saved", out, "errors:", errors.length);
for (const e of errors.slice(0, 8)) console.log("  ", e.slice(0, 220));
await browser.close();
