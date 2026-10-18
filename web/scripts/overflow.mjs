// Lists the elements that stick out past the right edge of the viewport on a route.
//   node scripts/overflow.mjs http://localhost:3000 /bank/ 390
import { createRequire } from "node:module";

const require = createRequire(new URL("../package.json", import.meta.url));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [base, route, widthArg = "390", who = "parent"] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
});
const page = await (await browser.createBrowserContext()).newPage();
await page.setViewport({ width: Number(widthArg), height: 900 });
await page.goto(`${base}/login/`, { waitUntil: "networkidle0" });
await page.type('input[type="email"]', `${who}@demo.studyroute.test`);
await page.type('input[type="password"]', "Sandbox#2026");
await page.click('button[type="submit"]');
await page.waitForSelector("main#main", { timeout: 20000 });
await page.goto(`${base}${route}`, { waitUntil: "networkidle0" });
await page.waitForSelector("main#main", { timeout: 20000 });
await sleep(2500);
const found = await page.evaluate(() => {
  const limit = window.innerWidth;
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.right > limit + 1) {
      // skip children of an element that scrolls on its own
      let scroller = false;
      for (let p = el.parentElement; p; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX;
        if (o === "auto" || o === "scroll" || o === "hidden") {
          scroller = true;
          break;
        }
      }
      if (!scroller)
        out.push(
          `${el.tagName.toLowerCase()}.${(el.getAttribute("class") || "").split(" ").slice(0, 4).join(".")}  right=${Math.round(rect.right)} width=${Math.round(rect.width)}  "${(el.textContent || "").trim().slice(0, 40)}"`,
        );
    }
  }
  return out.slice(0, 12);
});
console.log(found.join("\n") || "nothing sticks out");
await browser.close();
