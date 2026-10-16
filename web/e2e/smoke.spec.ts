import { expect, test } from "./fixtures";

const EMAIL = "parent@demo.studyroute.test";
const PASSWORD = "Sandbox#2026";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login/");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Hello, Demo Parent" })).toBeVisible();
}

test("the sign-in page says it is a sandbox and explains a wrong password", async ({
  page,
  problems,
}) => {
  await page.goto("/login/");
  await expect(page.getByRole("alert", { name: "Sandbox notice" })).toContainText(
    "Synthetic data, no real money moves",
  );
  await expect(page.getByRole("heading", { name: "Sign in to StudyRoute" })).toBeVisible();

  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Email or password is wrong.")).toBeVisible();
  await expect(page).toHaveURL(/\/login\/$/);
  // The browser itself logs the refused request; that is the one message this test expects.
  expect(problems).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
  problems.length = 0;
});

test("sign in, read the dashboard, compare providers and see the shortfall", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("alert", { name: "Sandbox notice" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Deadline planner" })).toContainText("On track");
  await expect(page.getByRole("region", { name: "Living-cost runway" })).toContainText("4.1");

  await page.getByRole("link", { name: "Compare providers" }).first().click();
  // Next's client router may drop the trailing slash of an exported page; the server serves both.
  await expect(page).toHaveURL(/\/compare\/?$/);
  // The request card and its live summary come first; the quotes card is empty until asked.
  const summary = page.getByRole("region", { name: "Your request" });
  await expect(summary).toContainText("GBP 10,000");
  await expect(page.getByText(/No quotes yet\. Press Get quotes/)).toBeVisible();
  await page.getByRole("radio", { name: /SHA/ }).check();
  await expect(summary).toContainText("SHA (shared)");
  await page.getByRole("radio", { name: /OUR/ }).check();
  await page.getByRole("button", { name: "Get quotes" }).click();

  const quotes = page.getByRole("region", { name: "Provider comparison table" });
  await expect(quotes).toContainText("Provider B (synthetic)");
  await expect(quotes.getByText("Best", { exact: true })).toBeVisible();
  await expect(page.getByText("Short by GBP 35.00")).toBeVisible();
  await expect(page.getByText("Currency-drop stress test")).toBeVisible();
  await expect(page.getByText("BDT 1,625,300.00").first()).toBeVisible();

  // The breakdown opens from the row menu and shows the engine's lines.
  await page.getByRole("button", { name: "Actions for Provider B (synthetic)" }).click();
  await page.getByRole("menuitem", { name: "View breakdown" }).click();
  const sheet = page.getByRole("dialog", { name: "Provider B (synthetic)" });
  await expect(sheet).toContainText("True total cost");
  await expect(sheet).toContainText("Indicative. Confirm with your AD bank.");
});

test("the session survives a reload without asking for the password again", async ({ page }) => {
  await signIn(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Hello, Demo Parent" })).toBeVisible();
});

test("the page never scrolls sideways", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("region", { name: "Living-cost runway" })).toBeVisible();
  const sideways = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(sideways).toBe(false);
});

test("a person who is not signed in is sent to the sign-in page", async ({ page }) => {
  await page.goto("/compare/");
  await expect(page).toHaveURL(/\/login\/?$/);
  await expect(page.getByRole("heading", { name: "Sign in to StudyRoute" })).toBeVisible();
});
