import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;

// The smoke test runs against the production build (web/out) served with the real security headers,
// so a Content-Security-Policy violation fails it. The API is answered by e2e/mock-api.ts, so no
// backend is needed. Build first: npm run build. Uses the Chrome that is installed on the machine.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: "chrome",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chrome",
        viewport: { width: 1440, height: 900 },
      },
    },
    { name: "mobile", use: { ...devices["Pixel 5"], channel: "chrome" } },
  ],
  webServer: {
    command: `node ../scripts/security/prod_like_server.mjs ${PORT} 8000`,
    url: `http://127.0.0.1:${PORT}/login/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
