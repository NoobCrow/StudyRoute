import { expect, test as base } from "@playwright/test";

import { mockApi } from "./mock-api";

/**
 * Every test gets the mocked API and fails if the page logs a console error, throws, or breaks the
 * Content-Security-Policy (the browser reports a violation as a console error).
 */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("console", (message) => {
        const expectedAnonymousRestore =
          message.location().url.endsWith("/api/v1/auth/browser/session") &&
          /status of 401/.test(message.text());
        if (message.type() === "error" && !expectedAnonymousRestore) problems.push(message.text());
      });
      page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
      await mockApi(page);
      await use(problems);
      expect(problems, "console errors and CSP violations").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
