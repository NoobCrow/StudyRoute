// Opens the interactive widgets of the production build under the strict Content-Security-Policy and
// fails on any console error (a CSP violation shows up as one): date picker, dropdowns, theme menu,
// command palette, the assistant sheet with a real question, the reset dialog and a quote.
//   node ../scripts/security/prod_like_server.mjs 8091 8000 &
//   node scripts/csp-interact.mjs http://127.0.0.1:8091
import { createRequire } from "node:module";

const require = createRequire(new URL("../package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const base = process.argv[2] ?? "http://127.0.0.1:8091";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
});
const page = await (await browser.createBrowserContext()).newPage();
await page.setViewport({ width: 1440, height: 1000 });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => {
  if (r.failure()?.errorText !== "net::ERR_ABORTED") errors.push(`request failed: ${r.url()}`);
});

let steps = 0;
async function step(name, action) {
  const before = errors.length;
  try {
    await action();
  } catch (e) {
    errors.push(`${name}: ${e.message}`);
  }
  await sleep(500);
  const added = errors.length - before;
  steps += 1;
  console.log(`${added === 0 ? "PASS" : "FAIL"}  ${name}`);
  for (const e of errors.slice(before, before + 3)) console.log(`      ${e.slice(0, 220)}`);
}
const click = (selector) => page.click(selector);
/** A real mouse click on the control with this text (Radix menus open on pointerdown, not on .click()). */
async function clickText(text, within = "body") {
  const handle = await page.evaluateHandle(
    (t, scope) => {
      const nodes = [
        ...document.querySelectorAll(
          `${scope} button, ${scope} [role=option], ${scope} [role=menuitemradio], ${scope} [cmdk-item]`,
        ),
      ];
      return (
        nodes.find((n) => n.textContent.trim() === t) ??
        nodes.find((n) => n.textContent.trim().startsWith(t)) ??
        null
      );
    },
    text,
    within,
  );
  const element = handle.asElement();
  if (!element) throw new Error(`no control with text "${text}"`);
  await element.click();
}

await page.goto(`${base}/login/`, { waitUntil: "networkidle0" });
await page.type('input[type="email"]', "parent@demo.studyroute.test");
await page.type('input[type="password"]', "Sandbox#2026");
await page.click('button[type="submit"]');
await page.waitForSelector("main#main", { timeout: 20000 });
await sleep(2000);

await step("deadline planner: open the date picker and choose a day", async () => {
  await click("#due-date");
  await page.waitForSelector("[role=dialog] table, [data-slot=calendar]");
  await page.evaluate(() =>
    document.querySelector("[data-slot=calendar] button[data-day]:not([disabled])")?.click(),
  );
});
await step("deadline planner: change the destination", async () => {
  await click("#plan-country");
  await page.waitForSelector("[role=option]");
  await clickText("Australia (AUD)").catch(() => page.keyboard.press("Escape"));
});
await step("rate card: change the currency", async () => {
  await click("#rate-currency");
  await page.waitForSelector("[role=option]");
  await page.keyboard.press("Escape");
});
await step("theme menu: dark, then light", async () => {
  await clickText("Theme:");
  await page.waitForSelector("[role=menuitemradio]");
  await clickText("Dark", "[role=menu]");
  await sleep(300);
  await clickText("Theme:");
  await page.waitForSelector("[role=menuitemradio]");
  await clickText("Light", "[role=menu]");
});
await step("command palette: open and close", async () => {
  await page.keyboard.down("Control");
  await page.keyboard.press("k");
  await page.keyboard.up("Control");
  await page.waitForSelector("[cmdk-input]");
  await page.keyboard.press("Escape");
});
await step("reset dialog: open and keep the data", async () => {
  await clickText("Reset my data");
  await page.waitForSelector("[role=alertdialog]");
  await clickText("Keep it", "[role=alertdialog]");
});
await step("runway: calculate", async () => {
  await clickText("Calculate runway");
});
await step("send plan: compare ways to send", async () => {
  await clickText("Compare ways to send");
  await page.waitForSelector("table");
});
await step("assistant: ask what-if question in the side sheet", async () => {
  await clickText("Ask the assistant");
  await page.waitForSelector("#chat-input");
  await page.type("#chat-input", "Plan GBP 10,000 tuition by 28 October");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.body.innerText.includes("Payment plan"), {
    timeout: 20000,
  });
  await page.keyboard.press("Escape");
});
await step("compare: get quotes and open the stress test", async () => {
  await page.evaluate(() => document.querySelector('a[href="/compare/"]')?.click());
  await page.waitForSelector("#q-country");
  await clickText("Get quotes");
  await page.waitForFunction(
    () =>
      document.body.innerText.includes("Currency-drop stress test") &&
      document.querySelectorAll("tbody tr").length > 4,
    { timeout: 20000 },
  );
});
await step("recipients: open the form select", async () => {
  await page.evaluate(() => document.querySelector('a[href="/recipients/"]')?.click());
  await page.waitForSelector("#r-type");
  await click("#r-type");
  await page.waitForSelector("[role=option]");
  await page.keyboard.press("Escape");
});

await browser.close();
const failed = errors.length;
console.log(`${steps} interactions, ${failed} problem(s)`);
process.exit(failed === 0 ? 0 : 1);
