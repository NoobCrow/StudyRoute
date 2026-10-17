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

// Measured against the device width, not window.innerWidth: a phone zooms out to fit wide content,
// which makes innerWidth grow with the page and hides the very problem this looks for.
async function scrollsSideways(page: import("@playwright/test").Page): Promise<boolean> {
  const width = page.viewportSize()?.width ?? 0;
  const content = await page.evaluate(() => document.documentElement.scrollWidth);
  return content > width + 1;
}

test("the page never scrolls sideways", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("region", { name: "Living-cost runway" })).toBeVisible();
  // The recent-payments table has loaded, so it is part of what is measured.
  await expect(page.getByRole("cell", { name: /INV-1/ })).toBeVisible();
  expect(await scrollsSideways(page)).toBe(false);
});

test("documents: a long file name wraps instead of widening the page", async ({ page }) => {
  await signIn(page);
  await page.goto("/documents/");
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
  await expect(page.getByText(/^offer-letter-x{100}\.txt$/)).toBeVisible();
  expect(await scrollsSideways(page)).toBe(false);
});

test("a person who is not signed in is sent to the sign-in page", async ({ page }) => {
  await page.goto("/compare/");
  await expect(page).toHaveURL(/\/login\/?$/);
  await expect(page.getByRole("heading", { name: "Sign in to StudyRoute" })).toBeVisible();
});

test("allowlist a recipient with the six-box MFA code and remove it again", async ({ page }) => {
  await signIn(page);
  await page.goto("/recipients/");
  await expect(page.getByRole("heading", { name: "Recipients" })).toBeVisible();
  await expect(page.getByText("1 recipient", { exact: true })).toBeVisible();
  await expect(page.getByText("Not allowlisted")).toBeVisible();

  const opener = page.getByRole("button", { name: "Allowlist with MFA" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Allowlist this recipient" });
  await expect(dialog.getByLabel("MFA code")).toBeFocused();
  await expect(dialog.getByRole("button", { name: "Confirm" })).toBeDisabled();
  await page.keyboard.type("246810");
  await dialog.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Allowlisted", { exact: true })).toBeVisible();
  await expect(page.getByText("1 allowlisted")).toBeVisible();

  await page.getByRole("button", { name: /Remove University of Example/ }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Remove" }).click();
  await page.getByRole("dialog", { name: "Remove from the allowlist" }).waitFor();
  await page.keyboard.type("246810");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Not allowlisted")).toBeVisible();
});

test("the add form checks the IBAN's check digits and keeps Save off until it is valid", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/recipients/#add");
  const save = page.getByRole("button", { name: "Save recipient" });
  await expect(save).toBeDisabled();
  await page.getByRole("button", { name: "Fill a synthetic example" }).click();
  await expect(page.getByText("The check digits are verified (ISO 13616, mod 97).")).toBeVisible();
  await expect(save).toBeEnabled();
  const iban = page.getByRole("textbox", { name: "IBAN" });
  await iban.fill("GB09EXMP12345612344821");
  await iban.blur(); // the message appears after the field is left, then follows every change
  await expect(page.getByText(/The check digits do not match/)).toBeVisible();
  await expect(save).toBeDisabled();
});

test("payments: filter by status, open a payment's sheet and cancel it", async ({ page }) => {
  await signIn(page);
  await page.goto("/payments/");
  await expect(page.getByRole("heading", { name: "Payments" })).toBeVisible();
  await expect(page.getByText("2 payments", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /Completed/ }).click();
  await expect(page.getByText("1 payment", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/status=completed/);
  await page.getByRole("tab", { name: /^All/ }).click();

  await page.getByRole("row", { name: /INV-1/ }).click();
  const sheet = page.getByRole("dialog", { name: "INV-1" });
  await expect(sheet).toContainText("Simulated. Nothing was sent to a real bank.");
  await sheet.getByRole("button", { name: "Cancel payment" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Cancel payment" }).click();
  await expect(page.getByRole("tab", { name: /In progress\s*0/ })).toBeVisible();
  await expect(page.getByText("Cancelled", { exact: true }).first()).toBeVisible();
});
