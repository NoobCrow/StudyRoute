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
  await page.getByRole("button", { name: "Get quotes" }).click();

  const table = page.getByRole("table").first();
  await expect(table).toContainText("Provider B (synthetic)");
  await expect(page.getByText("Lowest cost").first()).toBeVisible();
  await expect(page.getByText("Short by GBP 35.00")).toBeVisible();
  await expect(page.getByText("Currency-drop stress test")).toBeVisible();
  await expect(page.getByText("BDT 1,625,300.00").first()).toBeVisible();
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
