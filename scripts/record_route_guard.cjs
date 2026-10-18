/** Actual loopback-only UI/API demonstration. Synthetic accounts only, no real funds.
 * Build/start a fresh sandbox and the production-CSP static server first.
 * CHROME_PATH=/path/to/chromium node scripts/record_route_guard.cjs http://127.0.0.1:8098
 */
const fs = require("node:fs");
const path = require("node:path");
const cp = require("node:child_process");
const { createRequire } = require("node:module");
const req = createRequire(path.resolve(__dirname, "../web/package.json"));
const { chromium, expect } = req("@playwright/test");
const base = process.argv[2] || "http://127.0.0.1:8098";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw Error("Loopback sandbox only");
const dir = path.resolve(__dirname, "../dist/route-guard-recording");
fs.mkdirSync(dir, { recursive: true });
(async () => {
  let browser, context;
  const events = [],
    errors = [];
  const started = new Date();
  try {
    browser = await chromium.launch({
      executablePath:
        process.env.CHROME_PATH ||
        cp.execSync("command -v chromium").toString().trim(),
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });
    context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      recordVideo: { dir, size: { width: 1440, height: 1000 } },
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (
        /violates.*Content Security Policy|Content Security Policy.*violat/i.test(
          m.text(),
        )
      )
        errors.push(m.text());
    });
    async function step(label, fn) {
      await fn();
      events.push({ step: label, status: "PASS" });
      console.log("PASS", label);
    }
    await step("Real sandbox sign-in", async () => {
      await page.goto(base + "/login/");
      await page
        .getByLabel("Email", { exact: true })
        .fill("parent@demo.studyroute.test");
      await page.getByLabel("Password", { exact: true }).fill("Sandbox#2026");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "Hello, Demo Parent" }),
      ).toBeVisible({ timeout: 30000 });
    });
    let rid;
    await step(
      "Explicit institution declaration saved through actual UI/API",
      async () => {
        await page.goto(base + "/recipients/");
        await page
          .getByLabel("Name", { exact: true })
          .fill("MMU route demonstration (synthetic)");
        await page.getByLabel(/Bank BIC/).fill("WESTGB2L");
        await page
          .getByLabel("IBAN", { exact: true })
          .fill("GB82WEST12345698765432");
        await page
          .getByLabel("University payment-route policy", { exact: true })
          .selectOption("gb-manchester-metropolitan");
        await page.waitForTimeout(5000);
        const pending = page.waitForResponse(
          (r) =>
            r.url().endsWith("/recipients") && r.request().method() === "POST",
        );
        await page
          .getByRole("button", { name: "Save recipient", exact: true })
          .click();
        const response = await pending;
        if (response.status() !== 201)
          throw Error("Expected created recipient: " + response.status());
        rid = (await response.json()).recipient_id;
      },
    );
    await step(
      "Direct-bank tuition quote blocked by source-backed server response",
      async () => {
        await page.goto(
          base +
            "/compare/?destination=GB&amount=10000&purpose=TUITION&chargeCode=OUR&dueDate=2026-11-30&recipientId=" +
            encodeURIComponent(rid),
        );
        await expect(page.locator("#q-recipient")).toContainText(
          "MMU route demonstration",
        );
        await page.waitForTimeout(5000);
        const pending = page.waitForResponse(
          (r) => r.url().endsWith("/quotes") && r.request().method() === "POST",
        );
        await page
          .getByRole("button", { name: "Get quotes", exact: true })
          .click();
        const response = await pending;
        const body = await response.json();
        if (response.status() !== 422 || body.code !== "ROUTE_NOT_SUPPORTED")
          throw Error("Expected institution denial");
        await expect(
          page.getByText(
            /Do not create or submit a direct-bank tuition payment here/,
          ),
        ).toBeVisible();
        await page
          .getByText(
            /Do not create or submit a direct-bank tuition payment here/,
          )
          .scrollIntoViewIfNeeded();
        await page.waitForTimeout(1500);
        await page.screenshot({
          path: path.join(dir, "institution-route-blocked.png"),
          fullPage: false,
        });
        await page.waitForTimeout(10000);
      },
    );
    if (errors.length) throw Error(errors.join(";"));
    const video = await page.video().path();
    await context.close();
    context = null;
    fs.renameSync(video, path.join(dir, "StudyRoute_Route_Guard.webm"));
    fs.writeFileSync(
      path.join(dir, "route-guard-recording.json"),
      JSON.stringify(
        {
          started_utc: started.toISOString(),
          finished_utc: new Date().toISOString(),
          events,
          page_errors: errors,
          scope:
            "Actual local UI and API with production CSP. Synthetic recipient/account. No mocked API, no real bank/Flywire integration, no real money.",
        },
        null,
        2,
      ) + "\n",
    );
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
  }
})()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error(e.stack);
    process.exit(1);
  });
