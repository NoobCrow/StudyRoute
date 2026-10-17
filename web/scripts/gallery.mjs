// Takes the README screenshots of the running app. A driver (backend/app/scripts/gallery.py) starts this
// once and writes one JSON line per screenshot to its input; each answer is one JSON line on its output.
//   node scripts/gallery.mjs http://127.0.0.1:8090 ../submission/screenshots
//
// A shot is { out, route, who, width, height, theme, fullPage, steps }. One signed-in page is kept per
// person, size and theme, so the 10-a-minute sign-in limit is not an issue. Each step is one of
//   { click: "Get quotes" }           press the button or option with that text
//   { type: "#chat-input", text, enter }   type into a field (and press Enter)
//   { waitText: "Payment plan", count: 2 }   wait until the page shows this text (count times)
//   { clickRow: { row: ["Settled", "Example"], text: "Open" } }   the button in the table row holding all these texts
//   { scrollTo: "Smart send plan", offset: 110 }   bring the element with this text to the top
//   { scrollTop: true }               back to the top of the page
//   { press: "Escape" }  { wait: 800 }
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const require = createRequire(new URL("../package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [base, outDir] = process.argv.slice(2);
if (!base || !outDir) throw new Error("Usage: node scripts/gallery.mjs <base-url> <output-folder>");
fs.mkdirSync(outDir, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PASSWORD = "Sandbox#2026";

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
});
const pages = new Map();

async function signedInPage({ who = "parent", width = 1280, height = 1000, theme = "light" }) {
  const key = `${who}|${width}|${height}|${theme}`;
  const known = pages.get(key);
  if (known) return known;
  const page = await (await browser.createBrowserContext()).newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  await page.emulateMediaFeatures([
    { name: "prefers-color-scheme", value: theme },
    { name: "prefers-reduced-motion", value: "reduce" },
  ]);
  await page.goto(`${base}/login/`, { waitUntil: "networkidle0" });
  await page.waitForSelector('input[type="email"]');
  await page.type('input[type="email"]', `${who}@demo.studyroute.test`);
  await page.type('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForSelector("main#main", { timeout: 20000 });
  pages.set(key, page);
  return page;
}

/** A real mouse click on the control with this text (Radix menus open on pointerdown, not on .click()). */
async function clickText(page, text) {
  const handle = await page.evaluateHandle((t) => {
    const nodes = [
      ...document.querySelectorAll(
        "button, a, [role=option], [role=menuitem], [role=tab], [role=radio], label",
      ),
    ].filter((n) => n.offsetParent !== null);
    return (
      nodes.find((n) => n.textContent.trim() === t) ??
      nodes.find((n) => n.textContent.trim().startsWith(t)) ??
      nodes.find((n) => n.textContent.includes(t)) ??
      null
    );
  }, text);
  const element = handle.asElement();
  if (!element) throw new Error(`no control with text "${text}"`);
  await element.evaluate((n) => n.scrollIntoView({ block: "center" }));
  await element.click();
}

async function runStep(page, step) {
  if (step.click !== undefined) await clickText(page, step.click);
  else if (step.type) {
    await page.click(step.type.selector);
    await page.type(step.type.selector, step.type.text);
    if (step.type.enter) await page.keyboard.press("Enter");
  } else if (step.waitText !== undefined) {
    await page.waitForFunction(
      (t, n) => document.body.innerText.split(t).length - 1 >= n,
      { timeout: 30000 },
      step.waitText,
      step.count ?? 1,
    );
  } else if (step.clickRow) {
    const handle = await page.evaluateHandle(({ row, text }) => {
      const needles = [row].flat();
      const tr = [...document.querySelectorAll("tr")].find((r) =>
        needles.every((n) => r.textContent.includes(n)),
      );
      return (
        [...(tr?.querySelectorAll("button, a") ?? [])].find((b) => b.textContent.trim() === text) ??
        null
      );
    }, step.clickRow);
    const element = handle.asElement();
    if (!element) throw new Error(`no "${step.clickRow.text}" in the row "${step.clickRow.row}"`);
    await element.evaluate((n) => n.scrollIntoView({ block: "center" }));
    await element.click();
  } else if (step.scrollTo !== undefined) {
    await page.evaluate(
      (t, offset) => {
        const all = [
          ...document.querySelectorAll("h1, h2, h3, [data-slot=card-title], legend, p, span"),
        ];
        const hit =
          all.find((n) => n.textContent.trim() === t) ?? all.find((n) => n.textContent.includes(t));
        hit?.scrollIntoView({ block: "start" });
        window.scrollBy(0, -offset);
      },
      step.scrollTo,
      step.offset ?? 16,
    );
  } else if (step.scrollTop) await page.evaluate(() => window.scrollTo(0, 0));
  else if (step.press) await page.keyboard.press(step.press);
  else if (step.wait) await sleep(step.wait);
  else throw new Error(`unknown step ${JSON.stringify(step)}`);
  await sleep(250);
}

async function shoot(spec) {
  const page = await signedInPage(spec);
  if (spec.route) {
    await page.goto(`${base}${spec.route}`, { waitUntil: "networkidle0" });
    await page.waitForSelector("main#main", { timeout: 20000 });
  }
  await sleep(spec.settle ?? 1800);
  for (const step of spec.steps ?? []) await runStep(page, step);
  await sleep(400);
  // A full-page photograph of a scrolled page would show the sticky bars half way down.
  if (spec.fullPage) await page.evaluate(() => window.scrollTo(0, 0));
  const file = path.join(outDir, spec.out);
  await page.screenshot({ path: file, fullPage: Boolean(spec.fullPage) });
  return file;
}

const lines = readline.createInterface({ input: process.stdin });
let queue = Promise.resolve();
lines.on("line", (line) => {
  queue = queue.then(async () => {
    try {
      const spec = JSON.parse(line);
      if (spec.quit) {
        await browser.close();
        process.exit(0);
      }
      console.log(JSON.stringify({ ok: true, file: await shoot(spec) }));
    } catch (e) {
      console.log(JSON.stringify({ ok: false, error: String(e.message ?? e) }));
    }
  });
});
console.log(JSON.stringify({ ready: true }));
